"""C4 · review_popup mode 测试 · auto 默认不弹。"""

from __future__ import annotations

import time

import pytest

from client.review_popup import (
    HeadlessAutoAccept,
    ReviewMode,
    SmartReviewPopup,
    should_popup,
)
from shared.proto import IntentResult, ReviewDecision, Suggestion
from shared.types import EmotionEnum, IntentEnum, ReviewDecisionEnum, RiskEnum


def _mk_sug(risk=RiskEnum.LOW):
    return Suggestion(
        msg_id="sug_001",
        tenant_id="tenant_0001",
        inbound_msg_id="in_001",
        intent=IntentResult(intent=IntentEnum.GREETING, emotion=EmotionEnum.CALM, risk=risk, confidence=0.8),
        text="您好亲~",
        model_route="mock",
        generated_at=int(time.time()),
    )


def test_should_popup_auto_never():
    assert should_popup(_mk_sug(RiskEnum.LOW), ReviewMode.AUTO) is False
    assert should_popup(_mk_sug(RiskEnum.MEDIUM), ReviewMode.AUTO) is False
    assert should_popup(_mk_sug(RiskEnum.HIGH), ReviewMode.AUTO) is False


def test_should_popup_high_risk_only():
    assert should_popup(_mk_sug(RiskEnum.LOW), ReviewMode.HIGH_RISK_ONLY) is False
    assert should_popup(_mk_sug(RiskEnum.HIGH), ReviewMode.HIGH_RISK_ONLY) is True


def test_should_popup_manual_always():
    assert should_popup(_mk_sug(RiskEnum.LOW), ReviewMode.MANUAL) is True
    assert should_popup(_mk_sug(RiskEnum.HIGH), ReviewMode.MANUAL) is True


@pytest.mark.asyncio
async def test_smart_popup_auto_accepts_silently():
    submitted = []

    async def submit(decision):
        submitted.append(decision)
        return {"ok": True}

    popup = SmartReviewPopup(submit, mode=ReviewMode.AUTO)
    decision = await popup.show(_mk_sug(RiskEnum.HIGH))
    assert decision.decision == ReviewDecisionEnum.ACCEPT
    assert len(submitted) == 1


@pytest.mark.asyncio
async def test_headless_auto_accept_backward_compat():
    submitted = []

    async def submit(decision):
        submitted.append(decision)
        return {"ok": True}

    popup = HeadlessAutoAccept(submit)
    decision = await popup.show(_mk_sug())
    assert decision.decision == ReviewDecisionEnum.ACCEPT
