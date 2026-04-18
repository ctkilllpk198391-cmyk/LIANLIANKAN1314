"""F7 · 多账号容灾 · 主号涨红切小号 · 客户无感。

设计：
  - tenant.config.accounts: [{account_id, role, wxid}, ...]
  - tenant.config.active_account_id: 当前活跃
  - health_monitor 红灯 → on_red 回调 → auto_failover()
  - 切换写 account_failover_log 表

健康判断：F6 health_monitor 提供 level==green 的账号才能成为新主。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from server.db import session_scope
from server.health_monitor import HealthMonitor
from server.models import AccountFailoverLog
from server.tenant import TenantManager

logger = logging.getLogger(__name__)


@dataclass
class AccountInfo:
    account_id: str
    role: str         # primary | secondary
    wxid: str = ""
    is_active: bool = False
    health_level: Optional[str] = None
    health_score: Optional[float] = None


class AccountFailover:
    def __init__(self, tenant_manager: TenantManager, health_monitor: HealthMonitor):
        self.tenants = tenant_manager
        self.health = health_monitor
        self._active_runtime: dict[str, str] = {}   # tenant_id → active_account_id（运行时覆盖 yaml）

    def get_active_account_id(self, tenant_id: str) -> str:
        if tenant_id in self._active_runtime:
            return self._active_runtime[tenant_id]
        cfg = self.tenants.get(tenant_id)
        if cfg.active_account_id:
            return cfg.active_account_id
        if cfg.accounts:
            return cfg.accounts[0].get("account_id", "primary")
        return "primary"

    async def list_accounts(self, tenant_id: str) -> list[AccountInfo]:
        cfg = self.tenants.get(tenant_id)
        active = self.get_active_account_id(tenant_id)
        result: list[AccountInfo] = []

        if not cfg.accounts:
            # 默认单号
            snap = await self.health.get_status(tenant_id, "primary")
            return [AccountInfo(
                account_id="primary", role="primary", is_active=True,
                health_level=snap.level if snap else "green",
                health_score=snap.score if snap else 100.0,
            )]

        for acc in cfg.accounts:
            account_id = acc.get("account_id", "")
            snap = await self.health.get_status(tenant_id, account_id)
            result.append(AccountInfo(
                account_id=account_id,
                role=acc.get("role", "secondary"),
                wxid=acc.get("wxid", ""),
                is_active=(account_id == active),
                health_level=snap.level if snap else "green",
                health_score=snap.score if snap else 100.0,
            ))
        return result

    async def manual_switch(self, tenant_id: str, target_account_id: str) -> bool:
        cfg = self.tenants.get(tenant_id)
        valid_ids = {acc.get("account_id") for acc in cfg.accounts} or {"primary"}
        if target_account_id not in valid_ids:
            logger.warning("manual_switch invalid target=%s for tenant=%s", target_account_id, tenant_id)
            return False

        from_account = self.get_active_account_id(tenant_id)
        if from_account == target_account_id:
            return False

        await self._switch(tenant_id, from_account, target_account_id, "manual_switch", auto=False)
        return True

    async def auto_failover(self, tenant_id: str, account_id: str, reason: str = "auto") -> Optional[str]:
        """on_red 回调 · 选下一个 green 的 account 切换。返回新 account_id 或 None。"""
        cfg = self.tenants.get(tenant_id)
        if not cfg.accounts or len(cfg.accounts) <= 1:
            logger.warning("auto_failover: tenant=%s 无备用账号", tenant_id)
            return None

        from_account = account_id
        candidates = [
            acc.get("account_id") for acc in cfg.accounts
            if acc.get("account_id") and acc.get("account_id") != from_account
        ]

        for candidate in candidates:
            snap = await self.health.get_status(tenant_id, candidate)
            if snap is None or snap.level == "green":
                await self._switch(tenant_id, from_account, candidate, reason, auto=True)
                return candidate

        logger.error("auto_failover: tenant=%s 无健康备用账号 · 全部待人工", tenant_id)
        return None

    async def _switch(
        self,
        tenant_id: str,
        from_account: str,
        to_account: str,
        reason: str,
        auto: bool,
    ) -> None:
        self._active_runtime[tenant_id] = to_account
        async with session_scope() as session:
            session.add(
                AccountFailoverLog(
                    tenant_id=tenant_id,
                    from_account=from_account,
                    to_account=to_account,
                    reason=reason,
                    triggered_at=int(time.time()),
                    auto=1 if auto else 0,
                )
            )
        logger.warning(
            "[failover %s] tenant=%s · %s → %s · reason=%s",
            "auto" if auto else "manual", tenant_id, from_account, to_account, reason,
        )

    async def history(self, tenant_id: str, limit: int = 20) -> list[dict]:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(AccountFailoverLog)
                    .where(AccountFailoverLog.tenant_id == tenant_id)
                    .order_by(AccountFailoverLog.triggered_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [
                {
                    "from": r.from_account,
                    "to": r.to_account,
                    "reason": r.reason,
                    "triggered_at": r.triggered_at,
                    "auto": bool(r.auto),
                }
                for r in rows
            ]
