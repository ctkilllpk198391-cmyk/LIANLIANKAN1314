"""S2 · 心理学触发器测试。"""

from __future__ import annotations

import pytest

from server.psych_triggers import (
    DECISION_MATRIX,
    TRIGGER_INSTRUCTIONS,
    CustomerStage,
    TriggerType,
    build_psych_block,
    detect_stage,
    recommend,
    recommend_triggers,
)
from shared.types import EmotionEnum, IntentEnum


# ─── 阶段识别 ─────────────────────────────────────────────────────────────

def test_dormant_long_absence():
    stage = detect_stage(last_intent="greeting", days_since_last_message=45)
    assert stage == CustomerStage.DORMANT


def test_post_buy_after_purchase():
    stage = detect_stage(last_intent="chitchat", has_purchase_history=True)
    assert stage == CustomerStage.POST_BUY


def test_near_when_order():
    stage = detect_stage(last_intent="order")
    assert stage == CustomerStage.NEAR


def test_compare_when_negotiating():
    stage = detect_stage(last_intent="negotiation")
    assert stage == CustomerStage.COMPARE


def test_explore_default():
    stage = detect_stage(last_intent="greeting")
    assert stage == CustomerStage.EXPLORE


# ─── 触发器推荐 ──────────────────────────────────────────────────────────

def test_recommend_explore_inquiry_calm():
    triggers = recommend_triggers(IntentEnum.INQUIRY, EmotionEnum.CALM, CustomerStage.EXPLORE)
    assert TriggerType.RECIPROCITY in triggers


def test_recommend_near_excited_loss_aversion():
    triggers = recommend_triggers(IntentEnum.NEGOTIATION, EmotionEnum.EXCITED, CustomerStage.NEAR)
    assert TriggerType.SCARCITY in triggers
    assert TriggerType.LOSS_AVERSION in triggers


def test_recommend_complaint_only_reciprocity():
    """投诉 + 愤怒 → 不推销 · 仅互惠（先解决问题）"""
    triggers = recommend_triggers(IntentEnum.COMPLAINT, EmotionEnum.ANGRY, CustomerStage.COMPARE)
    assert TriggerType.RECIPROCITY in triggers
    assert TriggerType.SCARCITY not in triggers


def test_recommend_post_buy_commitment():
    triggers = recommend_triggers(IntentEnum.CHITCHAT, EmotionEnum.CALM, CustomerStage.POST_BUY)
    assert TriggerType.COMMITMENT in triggers


def test_recommend_unknown_combination_fallback():
    """未匹配 → fallback 互惠（不推销）"""
    triggers = recommend_triggers(IntentEnum.UNKNOWN, EmotionEnum.CALM, CustomerStage.EXPLORE)
    assert triggers == [TriggerType.RECIPROCITY]


# ─── psych_block 拼接 ────────────────────────────────────────────────────

def test_build_psych_block_includes_stage():
    block = build_psych_block([TriggerType.SCARCITY], CustomerStage.NEAR)
    assert "心理触发器" in block
    assert "near" in block
    assert "scarcity" in block.lower()


def test_build_psych_block_empty_returns_empty():
    assert build_psych_block([], CustomerStage.EXPLORE) == ""


def test_build_psych_block_multiple_triggers():
    block = build_psych_block(
        [TriggerType.SCARCITY, TriggerType.LOSS_AVERSION], CustomerStage.NEAR
    )
    assert "scarcity" in block.lower()
    assert "loss_aversion" in block.lower()


# ─── 综合 recommend ──────────────────────────────────────────────────────

def test_recommend_complete_flow_near_excited():
    rec = recommend(
        intent=IntentEnum.NEGOTIATION,
        emotion=EmotionEnum.EXCITED,
        last_intent="negotiation",
        last_intents_history=["inquiry", "negotiation"],
    )
    assert rec.stage == CustomerStage.NEAR
    assert TriggerType.SCARCITY in rec.triggers
    assert "scarcity" in rec.instructions.lower()


def test_recommend_dormant_customer():
    rec = recommend(
        intent=IntentEnum.GREETING,
        emotion=EmotionEnum.CALM,
        last_intent="greeting",
        days_since_last_message=60,
    )
    assert rec.stage == CustomerStage.DORMANT
    assert TriggerType.RECIPROCITY in rec.triggers


# ─── 决策矩阵完整性 ──────────────────────────────────────────────────────

def test_decision_matrix_all_triggers_have_instructions():
    """决策表里出现的每个 trigger 必须在 TRIGGER_INSTRUCTIONS 里有指令。"""
    used = {t for triggers in DECISION_MATRIX.values() for t in triggers}
    for t in used:
        assert t in TRIGGER_INSTRUCTIONS, f"missing instruction for {t}"
