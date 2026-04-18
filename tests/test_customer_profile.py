"""F2 · 客户档案引擎测试。"""

from __future__ import annotations

import time

import pytest

from server.customer_profile import CustomerProfileEngine
from shared.proto import InboundMsg, IntentResult, ReviewDecision, Suggestion
from shared.types import EmotionEnum, IntentEnum, ReviewDecisionEnum, RiskEnum


def _mk_msg(text="你好", chat_id="chat_001", sender="王姐"):
    return InboundMsg(
        tenant_id="tenant_0001",
        chat_id=chat_id,
        sender_id="user_001",
        sender_name=sender,
        text=text,
        timestamp=int(time.time()),
    )


def _mk_intent(intent=IntentEnum.GREETING, emotion=EmotionEnum.CALM, risk=RiskEnum.LOW):
    return IntentResult(intent=intent, emotion=emotion, risk=risk, confidence=0.8)


def _mk_suggestion(text="您好亲~"):
    return Suggestion(
        msg_id="sug_001",
        tenant_id="tenant_0001",
        inbound_msg_id="in_001",
        intent=_mk_intent(),
        text=text,
        model_route="mock",
        generated_at=int(time.time()),
    )


@pytest.mark.asyncio
async def test_get_or_create_new_customer(temp_db):
    eng = CustomerProfileEngine()
    snap = await eng.get_or_create("tenant_0001", "chat_999", sender_name="新客")
    assert snap.tenant_id == "tenant_0001"
    assert snap.chat_id == "chat_999"
    assert snap.nickname == "新客"
    assert snap.vip_tier == "C"
    assert snap.total_messages == 0


@pytest.mark.asyncio
async def test_get_or_create_idempotent(temp_db):
    eng = CustomerProfileEngine()
    s1 = await eng.get_or_create("tenant_0001", "chat_x", "A")
    s2 = await eng.get_or_create("tenant_0001", "chat_x", "B")  # 已存在 · nickname 不被覆盖
    assert s1.chat_id == s2.chat_id
    assert s2.nickname == "A"


@pytest.mark.asyncio
async def test_update_after_inbound_increments(temp_db):
    eng = CustomerProfileEngine()
    await eng.get_or_create("tenant_0001", "chat_001", "王姐")
    msg = _mk_msg("有货吗")
    intent = _mk_intent(IntentEnum.INQUIRY, EmotionEnum.ANXIOUS)
    await eng.update_after_inbound("tenant_0001", "chat_001", msg, intent)

    snap = await eng.get_or_create("tenant_0001", "chat_001")
    assert snap.total_messages == 1
    assert snap.last_intent == "inquiry"
    assert snap.last_emotion == "anxious"


@pytest.mark.asyncio
async def test_update_after_send_accept_increments(temp_db):
    eng = CustomerProfileEngine()
    await eng.get_or_create("tenant_0001", "chat_001", "王姐")
    sug = _mk_suggestion()
    decision = ReviewDecision(msg_id="sug_001", decision=ReviewDecisionEnum.ACCEPT, reviewed_at=int(time.time()))
    await eng.update_after_send("tenant_0001", "chat_001", sug, decision)

    snap = await eng.get_or_create("tenant_0001", "chat_001")
    assert snap.accepted_replies == 1


@pytest.mark.asyncio
async def test_update_with_purchase_promotes_tier(temp_db):
    eng = CustomerProfileEngine()
    await eng.get_or_create("tenant_0001", "chat_002", "李哥")
    sug = _mk_suggestion()
    decision = ReviewDecision(msg_id="sug_002", decision=ReviewDecisionEnum.ACCEPT, reviewed_at=int(time.time()))

    for _ in range(3):
        await eng.update_after_send(
            "tenant_0001", "chat_002", sug, decision, order_amount=199.0, sku="精华"
        )

    snap = await eng.get_or_create("tenant_0001", "chat_002")
    assert snap.vip_tier == "A"  # 月成交 ≥3 = A
    assert len(snap.purchase_history) == 3


def test_compute_vip_tier_from_history():
    eng = CustomerProfileEngine()
    now = int(time.time())
    h_a = [{"date": now, "sku": "x", "amount": 1}] * 3
    h_b = [{"date": now, "sku": "x", "amount": 1}]
    h_c_old = [{"date": now - 60 * 86400, "sku": "x", "amount": 1}] * 5
    assert eng.compute_vip_tier_from_history(h_a) == "A"
    assert eng.compute_vip_tier_from_history(h_b) == "B"
    assert eng.compute_vip_tier_from_history(h_c_old) == "C"  # 60 天前 · 不算近月


def test_render_for_prompt_empty_for_new():
    from server.customer_profile import CustomerProfileSnapshot
    snap = CustomerProfileSnapshot(
        tenant_id="t", chat_id="c", nickname="", preferred_addressing="",
        vip_tier="C", purchase_history=[], sensitive_topics=[], tags=[],
        last_intent=None, last_emotion=None, last_message_at=None,
        total_messages=0, accepted_replies=0, notes="",
    )
    assert CustomerProfileEngine.render_for_prompt(snap) == ""


def test_render_for_prompt_with_history_and_recent():
    from server.customer_profile import CustomerProfileSnapshot
    now = int(time.time())
    snap = CustomerProfileSnapshot(
        tenant_id="t", chat_id="c", nickname="王姐", preferred_addressing="姐",
        vip_tier="A",
        purchase_history=[{"date": now - 30 * 86400, "sku": "玉兰油", "amount": 299}],
        sensitive_topics=["怕油腻"],
        tags=["老顾客"],
        last_intent="inquiry", last_emotion="calm", last_message_at=now - 86400,
        total_messages=20, accepted_replies=15, notes="",
    )
    out = CustomerProfileEngine.render_for_prompt(snap)
    assert "王姐" in out
    assert "VIP-A" in out
    assert "玉兰油" in out
    assert "怕油腻" in out
    assert "老顾客" in out


def test_render_for_prompt_long_absence_alert():
    from server.customer_profile import CustomerProfileSnapshot
    now = int(time.time())
    snap = CustomerProfileSnapshot(
        tenant_id="t", chat_id="c", nickname="陈总", preferred_addressing="",
        vip_tier="B", purchase_history=[], sensitive_topics=[], tags=[],
        last_intent="chitchat", last_emotion="calm", last_message_at=now - 60 * 86400,
        total_messages=10, accepted_replies=8, notes="",
    )
    out = CustomerProfileEngine.render_for_prompt(snap)
    assert "60" in out and "未联系" in out


@pytest.mark.asyncio
async def test_tenant_isolation(temp_db):
    """同 chat_id 不同 tenant · 各自独立。"""
    eng = CustomerProfileEngine()
    s1 = await eng.get_or_create("tenant_0001", "shared_chat", "A 客")
    s2 = await eng.get_or_create("tenant_0002", "shared_chat", "B 客")
    assert s1.nickname == "A 客"
    assert s2.nickname == "B 客"
