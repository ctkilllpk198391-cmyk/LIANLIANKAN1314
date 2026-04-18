"""T3 · CustomerPipelineBuilder 测试 · ≥6 用例。"""

from __future__ import annotations

import time

import pytest

from server.customer_pipeline import CustomerPipelineBuilder, _calc_urgency, _infer_stage


# ─── helpers ─────────────────────────────────────────────────────────────────

async def _insert_customer(
    session,
    tenant_id: str,
    chat_id: str,
    vip_tier: str = "B",
    last_intent: str = "inquiry",
    last_message_at: int | None = None,
    last_emotion: str = "calm",
):
    from server.models import CustomerProfile as CPModel
    now = int(time.time())
    lma = last_message_at if last_message_at is not None else now
    session.add(CPModel(
        tenant_id=tenant_id,
        chat_id=chat_id,
        vip_tier=vip_tier,
        last_intent=last_intent,
        last_emotion=last_emotion,
        last_message_at=lma,
        total_messages=5,
        accepted_replies=2,
        updated_at=now,
    ))
    await session.flush()


# ─── 1. urgency 计算 ──────────────────────────────────────────────────────────

def test_urgency_order_1day():
    assert _calc_urgency("order", 1) == 3


def test_urgency_negotiation_2days():
    assert _calc_urgency("negotiation", 2) == 2


def test_urgency_inquiry_3days():
    assert _calc_urgency("inquiry", 3) == 1


def test_urgency_inquiry_0days():
    """inquiry 当天不触发紧急。"""
    assert _calc_urgency("inquiry", 0) == 0


def test_urgency_none_intent():
    assert _calc_urgency(None, 5) == 0


def test_urgency_order_0days():
    """order 当天不触发。"""
    assert _calc_urgency("order", 0) == 0


# ─── 2. stage 推断 ────────────────────────────────────────────────────────────

def test_infer_stage_order():
    assert _infer_stage("order") == "near"


def test_infer_stage_negotiation():
    assert _infer_stage("negotiation") == "compare"


def test_infer_stage_inquiry():
    assert _infer_stage("inquiry") == "explore"


def test_infer_stage_unknown():
    assert _infer_stage("greeting") == "explore"


# ─── 3. build() 空库返回空列表 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_empty_db(temp_db, loaded_tenants):
    builder = CustomerPipelineBuilder()
    result = await builder.build("tenant_0001")
    assert result == []


# ─── 4. build() 过滤 C 级客户 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_filters_tier_c(temp_db, loaded_tenants):
    from server.db import session_scope

    async with session_scope() as session:
        # C 级客户不应进入 pipeline
        await _insert_customer(session, "tenant_0001", "chat_c_user", vip_tier="C", last_intent="inquiry")

    builder = CustomerPipelineBuilder()
    result = await builder.build("tenant_0001")
    assert all(c.chat_id != "chat_c_user" for c in result)


# ─── 5. build() 过滤超过 30 天 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_filters_stale_over_30d(temp_db, loaded_tenants):
    from server.db import session_scope

    now = int(time.time())
    old_ts = now - 35 * 86400  # 35 天前

    async with session_scope() as session:
        await _insert_customer(
            session, "tenant_0001", "chat_stale",
            vip_tier="A", last_intent="inquiry",
            last_message_at=old_ts,
        )

    builder = CustomerPipelineBuilder()
    result = await builder.build("tenant_0001")
    assert all(c.chat_id != "chat_stale" for c in result)


# ─── 6. build() 过滤非高意向 intent ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_filters_low_intent(temp_db, loaded_tenants):
    from server.db import session_scope

    async with session_scope() as session:
        await _insert_customer(
            session, "tenant_0001", "chat_greeting",
            vip_tier="A", last_intent="greeting",
        )

    builder = CustomerPipelineBuilder()
    result = await builder.build("tenant_0001")
    assert all(c.chat_id != "chat_greeting" for c in result)


# ─── 7. build() 排序：urgency desc, days_since_last desc ──────────────────────

@pytest.mark.asyncio
async def test_build_sorted_by_urgency_then_days(temp_db, loaded_tenants):
    from server.db import session_scope

    now = int(time.time())

    async with session_scope() as session:
        # urgency 3 · 2 天前
        await _insert_customer(
            session, "tenant_0001", "chat_order",
            vip_tier="A", last_intent="order",
            last_message_at=now - 2 * 86400,
        )
        # urgency 1 · 3 天前
        await _insert_customer(
            session, "tenant_0001", "chat_inquiry",
            vip_tier="B", last_intent="inquiry",
            last_message_at=now - 3 * 86400,
        )
        # urgency 2 · 2 天前
        await _insert_customer(
            session, "tenant_0001", "chat_neg",
            vip_tier="A", last_intent="negotiation",
            last_message_at=now - 2 * 86400,
        )

    builder = CustomerPipelineBuilder()
    result = await builder.build("tenant_0001")

    # urgency 顺序：3 > 2 > 1
    urgencies = [c.urgency for c in result]
    assert urgencies == sorted(urgencies, reverse=True)
    assert result[0].chat_id == "chat_order"


# ─── 8. build() 包含正确字段 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_has_required_fields(temp_db, loaded_tenants):
    from server.db import session_scope

    now = int(time.time())

    async with session_scope() as session:
        await _insert_customer(
            session, "tenant_0001", "chat_ok",
            vip_tier="A", last_intent="order",
            last_message_at=now - 86400,
        )

    builder = CustomerPipelineBuilder()
    result = await builder.build("tenant_0001")

    assert len(result) == 1
    c = result[0]
    assert c.chat_id == "chat_ok"
    assert c.vip_tier == "A"
    assert c.urgency == 3
    assert c.stage == "near"
    assert isinstance(c.pending_value_estimate, float)
    assert c.pending_value_estimate > 0


# ─── 9. build() max_count 限制 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_max_count(temp_db, loaded_tenants):
    from server.db import session_scope

    now = int(time.time())

    async with session_scope() as session:
        for i in range(5):
            await _insert_customer(
                session, "tenant_0001", f"chat_{i}",
                vip_tier="B", last_intent="inquiry",
                last_message_at=now - (i + 2) * 86400,
            )

    builder = CustomerPipelineBuilder()
    result = await builder.build("tenant_0001", max_count=3)
    assert len(result) <= 3
