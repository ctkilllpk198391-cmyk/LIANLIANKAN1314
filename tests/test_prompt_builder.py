"""prompt_builder 测试 · 防幻觉 + 风格继承 + 风险约束。"""

from __future__ import annotations

import pytest

from server.prompt_builder import build_system_prompt, build_user_prompt
from shared.proto import IntentResult
from shared.types import IntentEnum, RiskEnum


def _intent(name=IntentEnum.GREETING, risk=RiskEnum.LOW):
    return IntentResult(intent=name, confidence=0.8, risk=risk)


def test_system_prompt_contains_boss_name():
    p = build_system_prompt("连大哥", "直接简洁", _intent(), "客户A")
    assert "连大哥" in p


def test_system_prompt_anti_geo_hallucination():
    """防 AI 编造老板地理位置/家庭/年龄等。"""
    p = build_system_prompt("连大哥", "直接简洁", _intent(), "客户A")
    assert "不要编造" in p
    assert "地理位置" in p
    assert "家庭" in p
    assert "年龄" in p


def test_system_prompt_anti_forbidden_words():
    """防绝对化承诺词。"""
    p = build_system_prompt("连大哥", "直接简洁", _intent(), "客户A")
    for w in ["保证", "一定", "终身", "稳赚", "100%"]:
        assert w in p


def test_system_prompt_inherits_style_hints():
    p = build_system_prompt("连大哥", "用东北话风格 · 喜欢用'整'字", _intent(), "客户A")
    assert "东北话" in p
    assert "整" in p


def test_system_prompt_high_risk_block():
    p = build_system_prompt(
        "连大哥", "直接", _intent(IntentEnum.COMPLAINT, RiskEnum.HIGH), "客户"
    )
    assert "不直接承诺" in p
    assert "立即帮您核实" in p or "核实" in p


def test_system_prompt_medium_risk_block():
    p = build_system_prompt(
        "连大哥", "直接", _intent(IntentEnum.NEGOTIATION, RiskEnum.MEDIUM), "客户"
    )
    assert "数字必须精确" in p


def test_system_prompt_low_risk_simple():
    p = build_system_prompt("连大哥", "直接", _intent(), "客户")
    assert "自然温暖回复" in p


def test_system_prompt_empty_style_fallback():
    p = build_system_prompt("连大哥", "", _intent(), "客户")
    assert "直接、简洁" in p   # fallback 默认风格


def test_system_prompt_contains_intent_and_risk():
    p = build_system_prompt(
        "连大哥", "x", _intent(IntentEnum.NEGOTIATION, RiskEnum.MEDIUM), "客户A"
    )
    assert "negotiation" in p
    assert "medium" in p


def test_user_prompt_format():
    p = build_user_prompt("小张", "在么 多少钱")
    assert "小张" in p
    assert "在么 多少钱" in p


def test_user_prompt_empty_sender():
    p = build_user_prompt("", "在么")
    assert "客户" in p   # fallback 默认称呼


def test_system_prompt_first_person():
    """要求 AI 用第一人称（不要写"老板说"）。"""
    p = build_system_prompt("连大哥", "x", _intent(), "客户")
    assert "第一人称" in p
