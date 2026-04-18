"""T5 · 数据删除管理测试 · ≥4 用例。"""

from __future__ import annotations

import time

import pytest

from server.data_deletion import GRACE_DAYS, GRACE_SECONDS, DataDeletionManager
from server.db import session_scope
from server.models import AuditLog, CustomerProfile, DeletionRequest, Message, SentMessage, Suggestion


# ─── 辅助：插入测试数据 ──────────────────────────────────────────────────────

async def _seed_tenant_data(tenant_id: str) -> None:
    """插入完整 tenant 数据：消息 + 建议 + 已发 + 客户档案 + 审计日志。"""
    now = int(time.time())
    async with session_scope() as session:
        msg_id = f"msg_{tenant_id}_del"
        session.add(Message(
            msg_id=msg_id,
            tenant_id=tenant_id,
            chat_id="chat_del",
            sender_id="user_del",
            sender_name="待删客户",
            text="这条消息会被删",
            msg_type="text",
            timestamp=now,
        ))
        sug_id = f"sug_{tenant_id}_del"
        session.add(Suggestion(
            msg_id=sug_id,
            tenant_id=tenant_id,
            inbound_msg_id=msg_id,
            intent="greeting",
            risk="low",
            text="这条建议会被删",
            model_route="mock",
            generated_at=now,
        ))
        session.add(SentMessage(
            msg_id=sug_id,
            tenant_id=tenant_id,
            chat_id="chat_del",
            text="这条已发消息会被删",
            sent_at=now,
            success=1,
        ))
        session.add(CustomerProfile(
            tenant_id=tenant_id,
            chat_id="chat_del",
            vip_tier="C",
            updated_at=now,
        ))
        session.add(AuditLog(
            actor="test",
            action="seed",
            tenant_id=tenant_id,
            timestamp=now,
        ))


async def _count_rows(tenant_id: str) -> dict:
    """统计各表中 tenant 的行数。"""
    async with session_scope() as session:
        from sqlalchemy import func, select

        def count(model, col):
            return select(func.count()).select_from(model).where(col == tenant_id)

        return {
            "messages": (await session.execute(count(Message, Message.tenant_id))).scalar_one(),
            "suggestions": (await session.execute(count(Suggestion, Suggestion.tenant_id))).scalar_one(),
            "sent_messages": (await session.execute(count(SentMessage, SentMessage.tenant_id))).scalar_one(),
            "customer_profiles": (await session.execute(count(CustomerProfile, CustomerProfile.tenant_id))).scalar_one(),
            "audit_log": (await session.execute(count(AuditLog, AuditLog.tenant_id))).scalar_one(),
        }


# ─── 测试 ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_request_creates_pending(temp_db):
    """request() 创建 pending 状态的删除请求，返回 request_id。"""
    mgr = DataDeletionManager()
    request_id = await mgr.request("tenant_0001", reason="测试删除")
    assert request_id

    async with session_scope() as session:
        from sqlalchemy import select
        req = (
            await session.execute(
                select(DeletionRequest).where(DeletionRequest.request_id == request_id)
            )
        ).scalar_one_or_none()

    assert req is not None
    assert req.status == "pending"
    assert req.tenant_id == "tenant_0001"
    assert req.reason == "测试删除"
    assert req.grace_until > int(time.time())
    assert (req.grace_until - req.requested_at) == GRACE_SECONDS


@pytest.mark.asyncio
async def test_request_idempotent(temp_db):
    """同一 tenant 重复 request 返回同一 request_id（不重复创建）。"""
    mgr = DataDeletionManager()
    id1 = await mgr.request("tenant_0001")
    id2 = await mgr.request("tenant_0001")
    assert id1 == id2


@pytest.mark.asyncio
async def test_cancel_pending_request(temp_db):
    """cancel() 成功撤销 pending 请求。"""
    mgr = DataDeletionManager()
    request_id = await mgr.request("tenant_0001", reason="测试撤销")

    ok = await mgr.cancel(request_id)
    assert ok is True

    async with session_scope() as session:
        from sqlalchemy import select
        req = (
            await session.execute(
                select(DeletionRequest).where(DeletionRequest.request_id == request_id)
            )
        ).scalar_one_or_none()
    assert req.status == "cancelled"


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false(temp_db):
    """cancel() 对不存在的 request_id 返回 False。"""
    mgr = DataDeletionManager()
    ok = await mgr.cancel("nonexistent-uuid-xxxx")
    assert ok is False


@pytest.mark.asyncio
async def test_list_pending_returns_only_pending(temp_db):
    """list_pending() 只返回 pending 状态的请求。"""
    mgr = DataDeletionManager()

    id1 = await mgr.request("tenant_0001")
    id2 = await mgr.request("tenant_0002")
    # 撤销第二个
    await mgr.cancel(id2)

    pending = await mgr.list_pending()
    tenant_ids = [p["tenant_id"] for p in pending]
    assert "tenant_0001" in tenant_ids
    assert "tenant_0002" not in tenant_ids


@pytest.mark.asyncio
async def test_execute_overdue_deletes_data(temp_db):
    """execute_overdue() 真删超 grace 期数据，保留 training_queue。"""
    await _seed_tenant_data("tenant_0001")

    # 验证有数据
    before = await _count_rows("tenant_0001")
    assert before["messages"] >= 1

    # 手动插入一个已过期的删除请求
    now = int(time.time())
    async with session_scope() as session:
        session.add(DeletionRequest(
            request_id="overdue-req-001",
            tenant_id="tenant_0001",
            reason="测试过期删除",
            status="pending",
            requested_at=now - GRACE_SECONDS - 100,
            grace_until=now - 100,   # 已过期
        ))

    mgr = DataDeletionManager()
    count = await mgr.execute_overdue()
    assert count == 1

    # 验证数据已删
    after = await _count_rows("tenant_0001")
    assert after["messages"] == 0
    assert after["suggestions"] == 0
    assert after["sent_messages"] == 0
    assert after["customer_profiles"] == 0

    # 验证请求状态更新为 executed
    async with session_scope() as session:
        from sqlalchemy import select
        req = (
            await session.execute(
                select(DeletionRequest).where(DeletionRequest.request_id == "overdue-req-001")
            )
        ).scalar_one_or_none()
    assert req.status == "executed"
    assert req.executed_at is not None


@pytest.mark.asyncio
async def test_execute_overdue_not_yet_due(temp_db):
    """未到期的请求不会被 execute_overdue() 处理。"""
    await _seed_tenant_data("tenant_0001")
    mgr = DataDeletionManager()

    # 创建一个未过期请求
    await mgr.request("tenant_0001", reason="未过期")

    count = await mgr.execute_overdue()
    assert count == 0

    # 数据还在
    after = await _count_rows("tenant_0001")
    assert after["messages"] >= 1


@pytest.mark.asyncio
async def test_grace_days_constant():
    """GRACE_DAYS 为 30 天，GRACE_SECONDS 为 30 * 86400。"""
    assert GRACE_DAYS == 30
    assert GRACE_SECONDS == 30 * 86400


@pytest.mark.asyncio
async def test_get_by_tenant_all_statuses(temp_db):
    """get_by_tenant() 返回该 tenant 所有状态的请求。"""
    mgr = DataDeletionManager()
    id1 = await mgr.request("tenant_0001", reason="第一次")
    await mgr.cancel(id1)
    # 再建一个（前一个已 cancelled，允许再建）
    # 注意：idempotent 只在 pending 状态生效，cancelled 后可再建
    async with session_scope() as session:
        session.add(DeletionRequest(
            request_id="new-req-002",
            tenant_id="tenant_0001",
            reason="第二次",
            status="pending",
            requested_at=int(time.time()),
            grace_until=int(time.time()) + GRACE_SECONDS,
        ))

    results = await mgr.get_by_tenant("tenant_0001")
    statuses = {r["status"] for r in results}
    assert "cancelled" in statuses
    assert "pending" in statuses
