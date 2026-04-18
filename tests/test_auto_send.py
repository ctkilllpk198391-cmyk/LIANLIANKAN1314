"""F1 · 全自动决策引擎测试。"""

from __future__ import annotations

import time

import pytest

from server.auto_send import AutoSendDecider, AutoSendDecisionType
from server.notifier import BossNotifier
from shared.proto import IntentResult, Suggestion, TenantConfig
from shared.types import EmotionEnum, IntentEnum, RiskEnum


def _mk_tenant(auto=True, hi_block=True):
    return TenantConfig(
        tenant_id="tenant_0001",
        boss_name="连大哥",
        plan="pro",
        auto_send_enabled=auto,
        high_risk_block=hi_block,
    )


def _mk_suggestion(risk=RiskEnum.LOW, intent=IntentEnum.GREETING):
    return Suggestion(
        msg_id="sug_001",
        tenant_id="tenant_0001",
        inbound_msg_id="in_001",
        intent=IntentResult(intent=intent, emotion=EmotionEnum.CALM, risk=risk, confidence=0.8),
        text="您好亲~",
        model_route="mock",
        generated_at=int(time.time()),
    )


@pytest.mark.asyncio
async def test_default_auto_send_low_risk():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    decision = await decider.decide(_mk_suggestion(), _mk_tenant())
    assert decision.decision == AutoSendDecisionType.AUTO_SEND


@pytest.mark.asyncio
async def test_high_risk_blocked():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    sug = _mk_suggestion(risk=RiskEnum.HIGH, intent=IntentEnum.COMPLAINT)
    decision = await decider.decide(sug, _mk_tenant(hi_block=True))
    assert decision.decision == AutoSendDecisionType.BLOCKED_HIGH_RISK


@pytest.mark.asyncio
async def test_high_risk_disabled_block_passes():
    """如果 tenant.high_risk_block=False · 高风险也直发。"""
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    sug = _mk_suggestion(risk=RiskEnum.HIGH, intent=IntentEnum.COMPLAINT)
    decision = await decider.decide(sug, _mk_tenant(hi_block=False))
    assert decision.decision == AutoSendDecisionType.AUTO_SEND


@pytest.mark.asyncio
async def test_paused_blocks():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    decider.pause("tenant_0001", duration_sec=3600)
    decision = await decider.decide(_mk_suggestion(), _mk_tenant())
    assert decision.decision == AutoSendDecisionType.BLOCKED_PAUSED
    assert decision.paused_until is not None


@pytest.mark.asyncio
async def test_resume_clears_pause():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    decider.pause("tenant_0001", duration_sec=3600)
    assert decider.is_paused("tenant_0001")
    assert decider.resume("tenant_0001")
    assert not decider.is_paused("tenant_0001")


@pytest.mark.asyncio
async def test_unhealthy_red_blocks():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    decision = await decider.decide(_mk_suggestion(), _mk_tenant(), health_score=42, health_level="red")
    assert decision.decision == AutoSendDecisionType.BLOCKED_UNHEALTHY
    assert decision.health_score == 42


@pytest.mark.asyncio
async def test_review_required_when_disabled():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    decision = await decider.decide(_mk_suggestion(), _mk_tenant(auto=False))
    assert decision.decision == AutoSendDecisionType.REVIEW_REQUIRED


@pytest.mark.asyncio
async def test_trigger_send_pushes_ws():
    pushed = []

    async def fake_ws(tenant_id, payload):
        pushed.append((tenant_id, payload))

    decider = AutoSendDecider(notifier=BossNotifier(mock=True), ws_pusher=fake_ws)
    decision = await decider.decide(_mk_suggestion(), _mk_tenant())
    await decider.trigger_send(decision, account_id="primary")

    assert len(pushed) == 1
    assert pushed[0][0] == "tenant_0001"
    assert pushed[0][1]["type"] == "auto_send_command"
    assert pushed[0][1]["text"] == "您好亲~"


@pytest.mark.asyncio
async def test_trigger_send_skips_blocked():
    pushed = []

    async def fake_ws(tenant_id, payload):
        pushed.append(payload)

    decider = AutoSendDecider(notifier=BossNotifier(mock=True), ws_pusher=fake_ws)
    sug = _mk_suggestion(risk=RiskEnum.HIGH, intent=IntentEnum.COMPLAINT)
    decision = await decider.decide(sug, _mk_tenant())
    await decider.trigger_send(decision)
    assert pushed == []


@pytest.mark.asyncio
async def test_handle_decision_notifies_on_high_risk():
    notifier = BossNotifier(mock=True)
    decider = AutoSendDecider(notifier=notifier)
    sug = _mk_suggestion(risk=RiskEnum.HIGH, intent=IntentEnum.COMPLAINT)
    decision = await decider.decide(sug, _mk_tenant())
    await decider.handle_decision(decision, _mk_tenant())
    # async task · 等一下
    import asyncio
    await asyncio.sleep(0.05)
    assert notifier.sent_count >= 1
    assert "高风险" in notifier.get_log()[0]["title"]


def test_pause_duration_clamped():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    until = decider.pause("t1", duration_sec=10)  # 太短 · clamp 到 60
    assert until - int(time.time()) >= 60


def test_pause_auto_expires():
    decider = AutoSendDecider(notifier=BossNotifier(mock=True))
    # 直接塞一个过期 ts
    decider._pause_state["t1"] = int(time.time()) - 100
    assert not decider.is_paused("t1")
    assert "t1" not in decider._pause_state  # 自动清除
