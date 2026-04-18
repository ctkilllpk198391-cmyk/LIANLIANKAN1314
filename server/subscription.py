"""订阅生命周期 · trial / pro / flagship · 按月计费。"""

from __future__ import annotations

import logging
import time
from typing import Literal

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy import select

from server.audit import audit
from server.db import session_scope
from server.models import Base

logger = logging.getLogger(__name__)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), ForeignKey("tenants.tenant_id"), nullable=False)
    plan = Column(String(32), nullable=False)
    status = Column(String(32), nullable=False, default="active")
    started_at = Column(Integer, nullable=False)
    expires_at = Column(Integer, nullable=False)
    last_payment_id = Column(String(128))


SECONDS_PER_MONTH = 30 * 86400


class SubscriptionService:
    async def activate(
        self,
        tenant_id: str,
        plan: Literal["trial", "pro", "flagship"],
        months: int = 1,
        payment_id: str | None = None,
    ) -> Subscription:
        now = int(time.time())
        async with session_scope() as session:
            current = (
                await session.execute(
                    select(Subscription)
                    .where(Subscription.tenant_id == tenant_id)
                    .where(Subscription.status == "active")
                    .order_by(Subscription.expires_at.desc())
                )
            ).scalars().first()

            if current and current.expires_at > now:
                start = current.expires_at
            else:
                start = now

            sub = Subscription(
                tenant_id=tenant_id,
                plan=plan,
                status="active",
                started_at=start,
                expires_at=start + months * SECONDS_PER_MONTH,
                last_payment_id=payment_id,
            )
            session.add(sub)
            await session.flush()
            sub_id = sub.id

        await audit.log(
            actor="server",
            action="subscription_activated",
            tenant_id=tenant_id,
            meta={"plan": plan, "months": months, "payment_id": payment_id},
        )
        # 重新从 DB 读出（防 detached）
        async with session_scope() as session:
            return (
                await session.execute(select(Subscription).where(Subscription.id == sub_id))
            ).scalar_one()

    async def is_active(self, tenant_id: str) -> bool:
        now = int(time.time())
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(Subscription)
                    .where(Subscription.tenant_id == tenant_id)
                    .where(Subscription.status == "active")
                    .where(Subscription.expires_at > now)
                )
            ).scalars().first()
        return row is not None

    async def expiring_soon(self, days: int = 7) -> list[str]:
        cutoff = int(time.time()) + days * 86400
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(Subscription.tenant_id)
                    .where(Subscription.status == "active")
                    .where(Subscription.expires_at <= cutoff)
                )
            ).scalars().all()
        return list(set(rows))

    async def cancel(self, tenant_id: str) -> bool:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(Subscription)
                    .where(Subscription.tenant_id == tenant_id)
                    .where(Subscription.status == "active")
                )
            ).scalars().all()
            for r in rows:
                r.status = "cancelled"
        await audit.log(actor="server", action="subscription_cancelled", tenant_id=tenant_id)
        return True
