"""shared.proto Pydantic 协议 round-trip 测试。"""

from __future__ import annotations

import time

import pytest
from pydantic import ValidationError

from shared.proto import (
    InboundMsg,
    IntentResult,
    ReviewDecision,
    SendAck,
    Suggestion,
)
from shared.types import IntentEnum, ReviewDecisionEnum, RiskEnum


def test_inbound_msg_minimal():
    msg = InboundMsg(
        tenant_id="tenant_0001",
        chat_id="wxid_chat",
        sender_id="wxid_sender",
        text="在么",
        timestamp=int(time.time()),
    )
    assert msg.msg_type == "text"
    assert msg.text == "在么"


def test_inbound_msg_strips():
    msg = InboundMsg(
        tenant_id="t",
        chat_id="c",
        sender_id="s",
        text="  hello  ",
        timestamp=0,
    )
    assert msg.text == "hello"


def test_intent_result_validates_confidence():
    ir = IntentResult(intent=IntentEnum.GREETING, confidence=0.9, risk=RiskEnum.LOW)
    assert ir.confidence == 0.9
    with pytest.raises(ValidationError):
        IntentResult(intent=IntentEnum.GREETING, confidence=1.5, risk=RiskEnum.LOW)


def test_suggestion_enforces_max_length():
    long_text = "x" * 301
    with pytest.raises(ValidationError):
        Suggestion(
            msg_id="sug_1",
            tenant_id="t",
            inbound_msg_id="in_1",
            intent=IntentResult(intent=IntentEnum.GREETING, confidence=0.5, risk=RiskEnum.LOW),
            text=long_text,
            model_route="hermes_default",
            generated_at=0,
        )


def test_suggestion_round_trip():
    sug = Suggestion(
        msg_id="sug_1",
        tenant_id="t",
        inbound_msg_id="in_1",
        intent=IntentResult(intent=IntentEnum.GREETING, confidence=0.5, risk=RiskEnum.LOW),
        text="您好",
        model_route="hermes_default",
        generated_at=123,
    )
    payload = sug.model_dump()
    reborn = Suggestion.model_validate(payload)
    assert reborn.text == "您好"
    assert reborn.intent.intent == IntentEnum.GREETING


def test_review_decision_edit():
    rd = ReviewDecision(
        msg_id="sug_1",
        decision=ReviewDecisionEnum.EDIT,
        edited_text="您好，请问需要点啥？",
        reviewed_at=int(time.time()),
    )
    assert rd.edited_text and rd.decision.value == "edit"


def test_send_ack_failure():
    ack = SendAck(msg_id="x", sent_at=0, success=False, error="timeout")
    assert ack.error == "timeout"
