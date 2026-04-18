"""F5 · classifier hybrid + emotion 测试。"""

from __future__ import annotations

import pytest

from server.classifier import IntentClassifier
from shared.types import EmotionEnum, IntentEnum, RiskEnum


# ─── 规则模式 · 意图 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_rule_mode_inquiry():
    c = IntentClassifier(mode="rule")
    r = await c.classify("这个面霜多少钱啊")
    assert r.intent == IntentEnum.INQUIRY
    assert r.confidence >= 0.4


@pytest.mark.asyncio
async def test_rule_mode_complaint_high_risk():
    c = IntentClassifier(mode="rule")
    r = await c.classify("这是假货 我要退款 投诉")
    assert r.intent == IntentEnum.COMPLAINT
    assert r.risk == RiskEnum.HIGH


@pytest.mark.asyncio
async def test_rule_mode_money_lifts_risk():
    c = IntentClassifier(mode="rule")
    r = await c.classify("便宜点 99 元行么")
    assert r.risk in (RiskEnum.MEDIUM, RiskEnum.HIGH)


# ─── 规则模式 · 情绪 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_emotion_calm_default():
    c = IntentClassifier(mode="rule")
    r = await c.classify("你好 在吗")
    assert r.emotion == EmotionEnum.CALM


@pytest.mark.asyncio
async def test_emotion_angry_keywords():
    c = IntentClassifier(mode="rule")
    r = await c.classify("差评！垃圾产品 退款")
    assert r.emotion == EmotionEnum.ANGRY


@pytest.mark.asyncio
async def test_emotion_anxious_keywords():
    c = IntentClassifier(mode="rule")
    r = await c.classify("快点 急用啊")
    assert r.emotion == EmotionEnum.ANXIOUS


@pytest.mark.asyncio
async def test_emotion_excited_keywords():
    c = IntentClassifier(mode="rule")
    r = await c.classify("买买买 现在就要")
    assert r.emotion == EmotionEnum.EXCITED


@pytest.mark.asyncio
async def test_emotion_question_marks_anxious():
    c = IntentClassifier(mode="rule")
    r = await c.classify("在吗???在不在?")
    assert r.emotion == EmotionEnum.ANXIOUS


@pytest.mark.asyncio
async def test_emotion_short_excited():
    c = IntentClassifier(mode="rule")
    r = await c.classify("好!!")
    assert r.emotion == EmotionEnum.EXCITED


# ─── Hybrid 模式 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hybrid_high_confidence_uses_rule():
    c = IntentClassifier(mode="hybrid")  # llm_client=None
    r = await c.classify("差评 投诉 退款 假货")
    assert r.intent == IntentEnum.COMPLAINT
    assert r.confidence >= 0.6


@pytest.mark.asyncio
async def test_hybrid_low_confidence_no_llm_fallback_to_rule():
    """confidence 低 · 无 llm_client → 仍用 rule 兜底（不抛错）。"""
    c = IntentClassifier(mode="hybrid")  # 无 llm_client
    r = await c.classify("这是个完全不在关键词库里的奇怪句子")
    assert r is not None
    assert r.intent == IntentEnum.UNKNOWN


@pytest.mark.asyncio
async def test_llm_mode_with_mock_client():
    """mode=llm + 提供 mock client 返回 JSON · 应解析。"""

    class MockLLM:
        async def respond(self, prompt, tenant_id, model_route, max_tokens=120, system=None, **kwargs):
            return '{"intent": "negotiation", "emotion": "anxious", "risk": "medium", "confidence": 0.85}'

    c = IntentClassifier(mode="llm", llm_client=MockLLM())
    r = await c.classify("能不能再便宜点啊 我急用")
    assert r.intent == IntentEnum.NEGOTIATION
    assert r.emotion == EmotionEnum.ANXIOUS
    assert r.risk == RiskEnum.MEDIUM


@pytest.mark.asyncio
async def test_llm_mode_malformed_json_falls_back():
    """LLM 返回非 JSON · 应 fallback 到 rule。"""

    class BrokenLLM:
        async def respond(self, **kwargs):
            return "我觉得是询价吧不太确定"

    c = IntentClassifier(mode="llm", llm_client=BrokenLLM())
    r = await c.classify("便宜点")
    # 应该 fallback 到 rule_result · NEGOTIATION
    assert r.intent in (IntentEnum.NEGOTIATION, IntentEnum.UNKNOWN)
