"""F4 · 跟进序列测试。"""

from __future__ import annotations

import time

import pytest

from server.follow_up import FollowUpEngine, TEMPLATES, TYPE_DELAYS
from server.models import FollowUpTask
from server.db import session_scope
from sqlalchemy import select


@pytest.mark.asyncio
async def test_schedule_creates_pending_task(temp_db):
    eng = FollowUpEngine()
    tid = await eng.schedule("tenant_0001", "chat_001", "unpaid_30min", sender_name="王姐")
    assert tid.startswith("fu_")

    tasks = await eng.list_for_tenant("tenant_0001")
    assert len(tasks) == 1
    assert tasks[0]["task_type"] == "unpaid_30min"
    assert tasks[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_schedule_unknown_type_raises(temp_db):
    eng = FollowUpEngine()
    with pytest.raises(ValueError):
        await eng.schedule("tenant_0001", "chat_001", "unknown_type")


@pytest.mark.asyncio
async def test_schedule_after_order_creates_4(temp_db):
    eng = FollowUpEngine()
    ids = await eng.schedule_after_order("tenant_0001", "chat_002", sender_name="李哥")
    assert len(ids) == 4
    tasks = await eng.list_for_tenant("tenant_0001")
    types = {t["task_type"] for t in tasks}
    assert types == {"unpaid_30min", "paid_1day", "satisfaction_7d", "repurchase_30d"}


@pytest.mark.asyncio
async def test_cancel_pending(temp_db):
    eng = FollowUpEngine()
    tid = await eng.schedule("tenant_0001", "chat_x", "paid_1day")
    assert await eng.cancel(tid) is True
    assert await eng.cancel(tid) is False  # already cancelled


@pytest.mark.asyncio
async def test_tick_picks_due_tasks(temp_db):
    sent = []

    async def sender(tenant_id, chat_id, text, task_id):
        sent.append((tenant_id, chat_id, text, task_id))
        return True

    eng = FollowUpEngine(send_callback=sender)
    tid = await eng.schedule("tenant_0001", "chat_x", "unpaid_30min")

    # 手动改 scheduled_at 到过去
    async with session_scope() as session:
        row = (await session.execute(
            select(FollowUpTask).where(FollowUpTask.task_id == tid)
        )).scalar_one()
        row.scheduled_at = int(time.time()) - 60

    n = await eng.tick()
    assert n == 1
    assert len(sent) == 1
    assert TEMPLATES["unpaid_30min"] in sent[0][2]


@pytest.mark.asyncio
async def test_tick_no_due_tasks(temp_db):
    eng = FollowUpEngine()
    await eng.schedule("tenant_0001", "chat_x", "repurchase_30d")  # 30 天后 · 不到期
    n = await eng.tick()
    assert n == 0


@pytest.mark.asyncio
async def test_tick_send_failure_marks_failed(temp_db):
    async def failing_sender(tenant_id, chat_id, text, task_id):
        return False

    eng = FollowUpEngine(send_callback=failing_sender)
    tid = await eng.schedule("tenant_0001", "chat_x", "unpaid_30min")
    async with session_scope() as session:
        row = (await session.execute(
            select(FollowUpTask).where(FollowUpTask.task_id == tid)
        )).scalar_one()
        row.scheduled_at = int(time.time()) - 60

    await eng.tick()
    tasks = await eng.list_for_tenant("tenant_0001")
    assert tasks[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_list_filter_by_status(temp_db):
    eng = FollowUpEngine()
    await eng.schedule("tenant_0001", "c1", "unpaid_30min")
    await eng.schedule("tenant_0001", "c2", "paid_1day")
    pending = await eng.list_for_tenant("tenant_0001", status="pending")
    assert len(pending) == 2
    sent = await eng.list_for_tenant("tenant_0001", status="sent")
    assert len(sent) == 0


def test_delay_constants():
    assert TYPE_DELAYS["unpaid_30min"] == 1800
    assert TYPE_DELAYS["repurchase_30d"] == 30 * 86400
