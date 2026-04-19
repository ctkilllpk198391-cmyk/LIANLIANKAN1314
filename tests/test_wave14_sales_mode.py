"""Wave 14 · 成交引导 · 销售脑 prompt + purchase_signal intent 单测.

覆盖:
- shared.types.IntentEnum 含 PURCHASE_SIGNAL + HESITATION
- classifier 命中购买信号关键词 → PURCHASE_SIGNAL
- classifier 命中犹豫关键词 → HESITATION
- prompt_builder._render_sales_block 按 intent 切策略
- build_system_prompt 最终含销售模式段
- 10 种子对话 e2e · 意图分类 + 销售段验证
"""

from __future__ import annotations

import pytest

from server.classifier import IntentClassifier
from server.prompt_builder import _render_sales_block, build_system_prompt
from shared.proto import IntentResult
from shared.types import EmotionEnum, IntentEnum, RiskEnum


def _intent(value: IntentEnum, risk: RiskEnum = RiskEnum.LOW) -> IntentResult:
    return IntentResult(intent=value, confidence=0.8, risk=risk, emotion=EmotionEnum.CALM)


# ── 1. 枚举扩展 ──────────────────────────────────────────────────────────────

def test_intent_enum_has_purchase_signal():
    assert IntentEnum.PURCHASE_SIGNAL.value == "purchase_signal"
    assert IntentEnum.HESITATION.value == "hesitation"


# ── 2. classifier 分类 ───────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("怎么买啊", IntentEnum.PURCHASE_SIGNAL),
    ("要一份", IntentEnum.PURCHASE_SIGNAL),
    ("我要这个", IntentEnum.PURCHASE_SIGNAL),
    ("想想再说", IntentEnum.HESITATION),
    ("再考虑考虑", IntentEnum.HESITATION),
    ("再看看", IntentEnum.HESITATION),
    ("在吗", IntentEnum.GREETING),
    ("多少钱", IntentEnum.INQUIRY),
    ("拍下了", IntentEnum.ORDER),
    ("便宜点", IntentEnum.NEGOTIATION),
])
@pytest.mark.asyncio
async def test_classifier_detects_sales_intents(text, expected):
    clf = IntentClassifier(mode="rule")
    result = await clf.classify(text)
    assert result.intent == expected, f"text={text!r} got {result.intent.value}"


# ── 3. prompt_builder sales block ────────────────────────────────────────────

def test_render_sales_block_for_purchase_signal():
    block = _render_sales_block(IntentEnum.PURCHASE_SIGNAL)
    assert "闭单" in block
    assert "确认" in block
    assert "销售模式" in block


def test_render_sales_block_for_hesitation():
    block = _render_sales_block(IntentEnum.HESITATION)
    assert "限时" in block or "活动" in block
    assert "赠品" in block or "折扣" in block
    assert "留余地" in block


def test_render_sales_block_for_inquiry():
    block = _render_sales_block(IntentEnum.INQUIRY)
    assert "报价" in block
    assert "紧迫" in block or "活动" in block


def test_render_sales_block_for_negotiation():
    block = _render_sales_block(IntentEnum.NEGOTIATION)
    assert "赠品" in block or "底线" in block


def test_render_sales_block_skips_non_sales_intents():
    for i in (IntentEnum.GREETING, IntentEnum.CHITCHAT, IntentEnum.COMPLAINT,
              IntentEnum.SENSITIVE, IntentEnum.UNKNOWN):
        assert _render_sales_block(i) == "", f"intent={i} should skip sales block"


# ── 4. build_system_prompt 集成 ──────────────────────────────────────────────

def test_build_system_prompt_includes_sales_block_for_purchase():
    prompt = build_system_prompt(
        boss_name="张老板",
        style_hints="直接简洁",
        intent=_intent(IntentEnum.PURCHASE_SIGNAL, RiskEnum.MEDIUM),
    )
    assert "销售模式" in prompt
    assert "闭单" in prompt


def test_build_system_prompt_no_sales_block_for_greeting():
    prompt = build_system_prompt(
        boss_name="张老板",
        style_hints="直接简洁",
        intent=_intent(IntentEnum.GREETING),
    )
    assert "销售模式" not in prompt


# ── 5. 10 种子对话 e2e · intent 分类 + 销售段覆盖 ────────────────────────────

SEED_DIALOGS = [
    ("在吗", IntentEnum.GREETING, False),
    ("多少钱一份", IntentEnum.INQUIRY, True),
    ("能便宜点不", IntentEnum.NEGOTIATION, True),
    ("要一份", IntentEnum.PURCHASE_SIGNAL, True),
    ("怎么买", IntentEnum.PURCHASE_SIGNAL, True),
    ("我想想", IntentEnum.HESITATION, True),
    ("再看看", IntentEnum.HESITATION, True),
    ("拍下了", IntentEnum.ORDER, True),
    ("哈哈好的", IntentEnum.CHITCHAT, False),
    ("投诉你们", IntentEnum.COMPLAINT, False),
]


@pytest.mark.parametrize("text,expected_intent,has_sales_block", SEED_DIALOGS)
@pytest.mark.asyncio
async def test_seed_dialogs_intent_and_sales_block(text, expected_intent, has_sales_block):
    clf = IntentClassifier(mode="rule")
    result = await clf.classify(text)
    assert result.intent == expected_intent, f"{text!r} intent={result.intent.value}"

    prompt = build_system_prompt(
        boss_name="张老板",
        style_hints="直接简洁",
        intent=result,
    )
    if has_sales_block:
        assert "销售模式" in prompt, f"{text!r} 应包含销售模式段"
    else:
        assert "销售模式" not in prompt, f"{text!r} 不应包含销售模式段"
