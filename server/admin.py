"""server/admin.py · FDW F6 管理后台 · 激活码 / 客户列表 / 报表。

认证：X-Admin-Token header（独立于 device_token）
"""

from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Header, HTTPException
from sqlalchemy import func, select, text

from server.db import session_scope
from server.models import ActivationCode, DeviceBinding, Tenant

ADMIN_TOKEN = os.getenv("BAIYANG_ADMIN_TOKEN")


# ─── 依赖 ───────────────────────────────────────────────────────────────────

async def admin_required(x_admin_token: Optional[str] = Header(None)) -> str:
    """FastAPI dependency · 校验 X-Admin-Token header。"""
    if not ADMIN_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="BAIYANG_ADMIN_TOKEN not configured on server",
        )
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-Admin-Token",
        )
    return x_admin_token


# ─── 数据类 ─────────────────────────────────────────────────────────────────

@dataclass
class CustomerSummary:
    tenant_id: str
    boss_name: str
    plan: str
    health_score: float
    today_revenue: int
    last_active_at: Optional[int]
    device_count: int


@dataclass
class RevenueReport:
    start_date: str
    end_date: str
    total_tenants: int
    active_tenants: int
    codes_issued: int
    codes_activated: int
    plans: dict = field(default_factory=dict)


# ─── AdminService ────────────────────────────────────────────────────────────

class AdminService:
    """管理员操作：客户列表 / 激活码 / 报表。"""

    # ── 客户列表 ─────────────────────────────────────────────────────────────

    async def list_customers(self) -> list[dict]:
        """所有 tenant + plan + 健康分 + 今日成交 + 上次活跃。"""
        async with session_scope() as session:
            tenants = (await session.execute(select(Tenant))).scalars().all()
            result = []
            for t in tenants:
                # 上次心跳（近似上次活跃）
                last_hb_row = (
                    await session.execute(
                        select(func.max(DeviceBinding.last_heartbeat_at))
                        .where(DeviceBinding.tenant_id == t.tenant_id)
                        .where(DeviceBinding.revoked == 0)
                    )
                ).scalar_one_or_none()

                # 设备数
                dev_count = (
                    await session.execute(
                        select(func.count(DeviceBinding.device_token))
                        .where(DeviceBinding.tenant_id == t.tenant_id)
                        .where(DeviceBinding.revoked == 0)
                    )
                ).scalar_one_or_none() or 0

                result.append(
                    {
                        "tenant_id": t.tenant_id,
                        "boss_name": t.boss_name,
                        "plan": t.plan,
                        "health_score": 100.0,      # 实际健康分由 health_monitor 维护
                        "today_revenue": 0,          # 占位 · 接入 billing 后替换
                        "last_active_at": last_hb_row,
                        "device_count": dev_count,
                    }
                )
            return result

    async def get_customer_detail(self, tenant_id: str) -> dict:
        """单客户深度信息：基础信息 + 激活码列表 + 设备绑定。"""
        async with session_scope() as session:
            tenant = (
                await session.execute(select(Tenant).where(Tenant.tenant_id == tenant_id))
            ).scalar_one_or_none()
            if not tenant:
                raise HTTPException(status_code=404, detail=f"tenant {tenant_id} not found")

            codes = (
                await session.execute(
                    select(ActivationCode).where(
                        ActivationCode.activated_tenant_id == tenant_id
                    )
                )
            ).scalars().all()

            devices = (
                await session.execute(
                    select(DeviceBinding).where(DeviceBinding.tenant_id == tenant_id)
                )
            ).scalars().all()

            return {
                "tenant_id": tenant.tenant_id,
                "boss_name": tenant.boss_name,
                "plan": tenant.plan,
                "created_at": tenant.created_at,
                "activation_codes": [
                    {
                        "code": c.code,
                        "plan": c.plan,
                        "valid_days": c.valid_days,
                        "issued_at": c.issued_at,
                        "activated_at": c.activated_at,
                        "revoked": bool(c.revoked),
                    }
                    for c in codes
                ],
                "device_bindings": [
                    {
                        "device_token": d.device_token[:8] + "...",   # 脱敏
                        "machine_guid": d.machine_guid[:8] + "...",
                        "bound_at": d.bound_at,
                        "last_heartbeat_at": d.last_heartbeat_at,
                        "revoked": bool(d.revoked),
                    }
                    for d in devices
                ],
            }

    # ── 激活码 ───────────────────────────────────────────────────────────────

    async def issue_activation_code(
        self,
        plan: str = "pro",
        valid_days: int = 365,
    ) -> str:
        """生成激活码并入库，返回码字符串。"""
        rand = secrets.token_hex(8).upper()          # 16 hex chars
        code = f"WXA-{rand[:4]}-{rand[4:8]}-{rand[8:12]}-{rand[12:16]}"
        now = int(time.time())

        async with session_scope() as session:
            session.add(
                ActivationCode(
                    code=code,
                    plan=plan,
                    valid_days=valid_days,
                    issued_at=now,
                    activated_at=None,
                    activated_tenant_id=None,
                    revoked=0,
                )
            )

        return code

    async def revoke_code(self, code: str) -> None:
        """撤销激活码（已激活的设备不受影响 · 仅标记码本身）。"""
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(ActivationCode).where(ActivationCode.code == code)
                )
            ).scalar_one_or_none()
            if not row:
                raise HTTPException(status_code=404, detail=f"code {code} not found")
            row.revoked = 1

    # ── 报表 ─────────────────────────────────────────────────────────────────

    async def export_revenue_report(
        self,
        start_date: str,
        end_date: str,
    ) -> dict:
        """导出收入摘要（按 plan 分组激活码数量）。

        start_date / end_date 格式：YYYY-MM-DD
        """
        import datetime

        def _to_ts(date_str: str) -> int:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            return int(dt.timestamp())

        ts_start = _to_ts(start_date)
        ts_end = _to_ts(end_date) + 86400  # 包含结束当天

        async with session_scope() as session:
            # 发码量（按 plan）
            all_codes = (
                await session.execute(
                    select(ActivationCode).where(
                        ActivationCode.issued_at >= ts_start,
                        ActivationCode.issued_at < ts_end,
                    )
                )
            ).scalars().all()

            plans: dict[str, dict] = {}
            for c in all_codes:
                p = c.plan
                if p not in plans:
                    plans[p] = {"issued": 0, "activated": 0}
                plans[p]["issued"] += 1
                if c.activated_at:
                    plans[p]["activated"] += 1

            total_tenants = (
                await session.execute(select(func.count(Tenant.tenant_id)))
            ).scalar_one_or_none() or 0

            active_tenants = (
                await session.execute(
                    select(func.count(func.distinct(DeviceBinding.tenant_id))).where(
                        DeviceBinding.last_heartbeat_at >= ts_start,
                        DeviceBinding.last_heartbeat_at < ts_end,
                        DeviceBinding.revoked == 0,
                    )
                )
            ).scalar_one_or_none() or 0

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_tenants": total_tenants,
            "active_tenants": active_tenants,
            "codes_issued": len(all_codes),
            "codes_activated": sum(1 for c in all_codes if c.activated_at),
            "plans": plans,
        }

    # ── 健康总览 ─────────────────────────────────────────────────────────────

    async def health_overview(self) -> dict:
        """所有租户健康总览（设备在线数 + 最近心跳时间）。"""
        async with session_scope() as session:
            now = int(time.time())
            online_threshold = now - 3600  # 1 小时内有心跳 = 在线

            total_tenants = (
                await session.execute(select(func.count(Tenant.tenant_id)))
            ).scalar_one_or_none() or 0

            online_devices = (
                await session.execute(
                    select(func.count(DeviceBinding.device_token)).where(
                        DeviceBinding.last_heartbeat_at >= online_threshold,
                        DeviceBinding.revoked == 0,
                    )
                )
            ).scalar_one_or_none() or 0

            total_devices = (
                await session.execute(
                    select(func.count(DeviceBinding.device_token)).where(
                        DeviceBinding.revoked == 0
                    )
                )
            ).scalar_one_or_none() or 0

            total_codes = (
                await session.execute(select(func.count(ActivationCode.code)))
            ).scalar_one_or_none() or 0

            activated_codes = (
                await session.execute(
                    select(func.count(ActivationCode.code)).where(
                        ActivationCode.activated_at != None  # noqa: E711
                    )
                )
            ).scalar_one_or_none() or 0

        return {
            "timestamp": now,
            "total_tenants": total_tenants,
            "total_devices": total_devices,
            "online_devices": online_devices,
            "total_activation_codes": total_codes,
            "activated_codes": activated_codes,
        }
