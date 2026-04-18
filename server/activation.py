"""FDW F2 · 激活码系统 · 生成 / 激活 / 设备绑定 / 心跳 / 吊销。"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from typing import Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import ActivationCode, DeviceBinding

logger = logging.getLogger("baiyang.activation")

_OFFLINE_TTL_SECONDS = 7 * 24 * 3600  # 离线 7 天禁用


class ActivationService:

    # ── 生成激活码 ────────────────────────────────────────────────────────────

    @staticmethod
    def generate_code(plan: str = "pro", valid_days: int = 365) -> str:
        """格式：WXA-2026-XXXX-XXXX-XXXX · 落库 · 返回 code。"""
        parts = [secrets.token_hex(2).upper() for _ in range(3)]
        code = f"WXA-2026-{parts[0]}-{parts[1]}-{parts[2]}"

        import asyncio
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 调用方负责 await _save_code
            raise RuntimeError("use async generate_code_async in async context")
        loop.run_until_complete(ActivationService._save_code(code, plan, valid_days))
        return code

    @staticmethod
    async def generate_code_async(plan: str = "pro", valid_days: int = 365) -> str:
        """异步版 · 落库 · 返回 code。"""
        parts = [secrets.token_hex(2).upper() for _ in range(3)]
        code = f"WXA-2026-{parts[0]}-{parts[1]}-{parts[2]}"
        await ActivationService._save_code(code, plan, valid_days)
        logger.info("code generated: %s plan=%s valid_days=%d", code, plan, valid_days)
        return code

    @staticmethod
    async def _save_code(code: str, plan: str, valid_days: int) -> None:
        async with session_scope() as session:
            session.add(ActivationCode(
                code=code,
                plan=plan,
                valid_days=valid_days,
                issued_at=int(time.time()),
            ))

    # ── 激活 ──────────────────────────────────────────────────────────────────

    async def activate(self, code: str, machine_guid: str, tenant_id: str) -> str:
        """校验 code → 创建 device_token → 落库 → 返 token。

        machine_guid 为 None 时用 sha256(code) 兜底。
        """
        if not machine_guid:
            machine_guid = hashlib.sha256(code.encode()).hexdigest()[:32]

        async with session_scope() as session:
            row: Optional[ActivationCode] = (
                await session.execute(
                    select(ActivationCode).where(ActivationCode.code == code)
                )
            ).scalar_one_or_none()

            if row is None:
                raise ValueError(f"invalid activation code: {code}")
            if row.revoked:
                raise ValueError(f"activation code revoked: {code}")
            if row.activated_at is not None:
                raise ValueError(f"activation code already used: {code}")

            device_token = secrets.token_urlsafe(32)
            now = int(time.time())

            row.activated_at = now
            row.activated_tenant_id = tenant_id

            session.add(DeviceBinding(
                device_token=device_token,
                tenant_id=tenant_id,
                activation_code=code,
                machine_guid=machine_guid,
                bound_at=now,
                last_heartbeat_at=now,
            ))

        logger.info("activated code=%s tenant=%s", code, tenant_id)
        return device_token

    # ── 吊销激活码 ────────────────────────────────────────────────────────────

    async def revoke_code(self, code: str) -> None:
        async with session_scope() as session:
            row: Optional[ActivationCode] = (
                await session.execute(
                    select(ActivationCode).where(ActivationCode.code == code)
                )
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"code not found: {code}")
            row.revoked = 1
        logger.info("revoked code=%s", code)

    # ── 吊销设备 ──────────────────────────────────────────────────────────────

    async def revoke_device(self, device_token: str) -> None:
        async with session_scope() as session:
            row: Optional[DeviceBinding] = (
                await session.execute(
                    select(DeviceBinding).where(DeviceBinding.device_token == device_token)
                )
            ).scalar_one_or_none()
            if row is None:
                raise ValueError(f"device_token not found: {device_token}")
            row.revoked = 1
        logger.info("revoked device_token=%s", device_token[:8] + "...")

    # ── 心跳 ──────────────────────────────────────────────────────────────────

    async def heartbeat(self, device_token: str) -> bool:
        """更新 last_heartbeat_at。离线超 7 天则吊销 token 返 False，否则返 True。"""
        now = int(time.time())
        async with session_scope() as session:
            row: Optional[DeviceBinding] = (
                await session.execute(
                    select(DeviceBinding).where(DeviceBinding.device_token == device_token)
                )
            ).scalar_one_or_none()

            if row is None or row.revoked:
                return False

            # 检测离线超期（心跳时间早于 now - TTL）
            if now - row.last_heartbeat_at > _OFFLINE_TTL_SECONDS:
                row.revoked = 1
                logger.warning("device offline >7d, revoked: %s", device_token[:8] + "...")
                return False

            row.last_heartbeat_at = now
        return True

    # ── API 鉴权校验 ──────────────────────────────────────────────────────────

    async def is_valid(self, device_token: str) -> Optional[dict]:
        """返 {tenant_id, plan} 或 None（无效 / 已吊销）。"""
        async with session_scope() as session:
            binding: Optional[DeviceBinding] = (
                await session.execute(
                    select(DeviceBinding).where(DeviceBinding.device_token == device_token)
                )
            ).scalar_one_or_none()

            if binding is None or binding.revoked:
                return None

            # 检查激活码是否被吊销
            code_row: Optional[ActivationCode] = (
                await session.execute(
                    select(ActivationCode).where(ActivationCode.code == binding.activation_code)
                )
            ).scalar_one_or_none()

            if code_row is None or code_row.revoked:
                return None

            return {
                "tenant_id": binding.tenant_id,
                "plan": code_row.plan,
                "bound_at": binding.bound_at,
                "last_heartbeat_at": binding.last_heartbeat_at,
            }
