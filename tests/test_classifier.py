"""IntentClassifier 规则版测试。"""

from __future__ import annotations

import pytest

from server.classifier import IntentClassifier
from shared.types import IntentEnum, RiskEnum


@pytest.mark.asyncio
async def test_classify_greeting():
    clf = IntentClassifier()
    result = await clf.classify("在么？")
    assert result.intent == IntentEnum.GREETING
    assert result.risk == RiskEnum.LOW


@pytest.mark.asyncio
async def test_classify_inquiry():
    clf = IntentClassifier()
    result = await clf.classify("这个面膜多少钱？")
    assert result.intent == IntentEnum.INQUIRY
    # 含"钱"被升 medium
    assert result.risk == RiskEnum.MEDIUM


@pytest.mark.asyncio
async def test_classify_negotiation():
    clf = IntentClassifier()
    result = await clf.classify("再便宜点行不行")
    assert result.intent == IntentEnum.NEGOTIATION


@pytest.mark.asyncio
async def test_classify_complaint_high_risk():
    clf = IntentClassifier()
    result = await clf.classify("你这是假货，要投诉")
    assert result.intent == IntentEnum.COMPLAINT
    assert result.risk == RiskEnum.HIGH


@pytest.mark.asyncio
async def test_classify_sensitive_high_risk():
    clf = IntentClassifier()
    result = await clf.classify("我要找律师追责")
    assert result.intent == IntentEnum.SENSITIVE
    assert result.risk == RiskEnum.HIGH


@pytest.mark.asyncio
async def test_classify_big_amount_upgrades_risk():
    clf = IntentClassifier()
    result = await clf.classify("总价 3 万")
    # 含"万" 升 high
    assert result.risk == RiskEnum.HIGH


@pytest.mark.asyncio
async def test_classify_unknown_returns_low_confidence():
    clf = IntentClassifier()
    result = await clf.classify("?????")
    assert result.intent == IntentEnum.UNKNOWN
    assert result.confidence < 0.5
