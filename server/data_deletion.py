"""T5 · 数据删除管理 · GDPR 30 天 Grace Period。"""

from __future__ import annotations

import time
import uuid

from sqlalchemy import delete, select

from server.db import session_scope
from server.models import (
    AuditLog,
    CustomerProfile,
    DeletionRequest,
    Message,
    SentMessage,
    Suggestion,
)

GRACE_DAYS = 30
GRACE_SECONDS = GRACE_DAYS * 86400


class DataDeletionManager:
    """管理 tenant 删除请求 · 30 天宽限期 · GDPR 合规。"""

    async def request(self, tenant_id: str, reason: str = "") -> str:
        """记录删除请求，返回 request_id。30 天后 cron 真删。"""
        request_id = str(uuid.uuid4())
        now = int(time.time())
        grace_until = now + GRACE_SECONDS

        async with session_scope() as session:
            # 若已有 pending 请求，直接返回已有的
            existing = (
                await session.execute(
                    select(DeletionRequest)
                    .where(DeletionRequest.tenant_id == tenant_id)
                    .where(DeletionRequest.status == "pending")
                )
            ).scalar_one_or_none()

            if existing:
                return existing.request_id

            session.add(DeletionRequest(
                request_id=request_id,
                tenant_id=tenant_id,
                reason=reason,
                status="pending",
                requested_at=now,
                grace_until=grace_until,
                executed_at=None,
            ))

        return request_id

    async def cancel(self, request_id: str) -> bool:
        """宽限期内撤销删除请求。"""
        async with session_scope() as session:
            req = (
                await session.execute(
                    select(DeletionRequest)
                    .where(DeletionRequest.request_id == request_id)
                    .where(DeletionRequest.status == "pending")
                )
            ).scalar_one_or_none()

            if req is None:
                return False

            req.status = "cancelled"

        return True

    async def list_pending(self) -> list[dict]:
        """所有待删请求（admin 查看）。"""
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(DeletionRequest)
                    .where(DeletionRequest.status == "pending")
                    .order_by(DeletionRequest.requested_at.asc())
                )
            ).scalars().all()

        return [
            {
                "request_id": r.request_id,
                "tenant_id": r.tenant_id,
                "reason": r.reason,
                "status": r.status,
                "requested_at": r.requested_at,
                "grace_until": r.grace_until,
                "days_remaining": max(0, (r.grace_until - int(time.time())) // 86400),
            }
            for r in rows
        ]

    async def get_by_tenant(self, tenant_id: str) -> list[dict]:
        """按 tenant 查询所有删除请求。"""
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(DeletionRequest)
                    .where(DeletionRequest.tenant_id == tenant_id)
                    .order_by(DeletionRequest.requested_at.desc())
                )
            ).scalars().all()

        return [
            {
                "request_id": r.request_id,
                "tenant_id": r.tenant_id,
                "reason": r.reason,
                "status": r.status,
                "requested_at": r.requested_at,
                "grace_until": r.grace_until,
                "executed_at": r.executed_at,
            }
            for r in rows
        ]

    async def execute_overdue(self) -> int:
        """每天 03:00 cron 调用。删除超过 grace 期的请求对应的 tenant 数据。

        删除：messages / suggestions / sent_messages / customer_profiles / audit_log
        保留：training_queue（按协议归 wechat_agent，已聚合）

        返回：成功删除的 tenant 数
        """
        now = int(time.time())
        deleted_count = 0

        async with session_scope() as session:
            overdue = (
                await session.execute(
                    select(DeletionRequest)
                    .where(DeletionRequest.status == "pending")
                    .where(DeletionRequest.grace_until <= now)
                )
            ).scalars().all()

        for req in overdue:
            tenant_id = req.tenant_id
            await self._delete_tenant_data(tenant_id)

            # 标记为 executed
            async with session_scope() as session:
                req_row = (
                    await session.execute(
                        select(DeletionRequest)
                        .where(DeletionRequest.request_id == req.request_id)
                    )
                ).scalar_one_or_none()
                if req_row:
                    req_row.status = "executed"
                    req_row.executed_at = int(time.time())

            deleted_count += 1

        return deleted_count

    async def _delete_tenant_data(self, tenant_id: str) -> None:
        """真删：按 tenant_id 删除原始数据。保留 training_queue。"""
        async with session_scope() as session:
            # 先删有 FK 依赖的子表
            await session.execute(
                delete(SentMessage).where(SentMessage.tenant_id == tenant_id)
            )
            await session.execute(
                delete(Suggestion).where(Suggestion.tenant_id == tenant_id)
            )
            await session.execute(
                delete(Message).where(Message.tenant_id == tenant_id)
            )
            await session.execute(
                delete(CustomerProfile).where(CustomerProfile.tenant_id == tenant_id)
            )
            await session.execute(
                delete(AuditLog).where(AuditLog.tenant_id == tenant_id)
            )
            # training_queue 不删（按协议归 wechat_agent）
