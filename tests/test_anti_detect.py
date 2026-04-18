"""S6 · 反检测套件测试。"""

from __future__ import annotations

import random

from server.anti_detect import (
    OPENING_VARIANTS,
    STALE_OPENINGS,
    detect_suspicion,
    humanize,
    inject_typo,
    vary_opening,
)


# ─── 错别字注入 ──────────────────────────────────────────────────────────

def test_inject_typo_zero_prob_no_change():
    text = "亲，今天的产品很不错的"
    assert inject_typo(text, prob=0.0) == text


def test_inject_typo_eventually_changes():
    """高概率 + 多次 · 至少有 1 次发生改变。"""
    text = "在的亲，今天的产品很不错的得"
    rng = random.Random(0)
    seen_change = False
    for _ in range(20):
        out = inject_typo(text, prob=1.0, rng=rng)
        if out != text:
            seen_change = True
            break
    assert seen_change


def test_inject_typo_no_replaceable_chars():
    text = "abc123"
    assert inject_typo(text, prob=1.0) == text


def test_inject_typo_empty():
    assert inject_typo("", prob=1.0) == ""


# ─── 开场白变体 ──────────────────────────────────────────────────────────

def test_vary_opening_replaces_stale():
    text = "亲，您好~ 这款是爆款"
    rng = random.Random(0)
    out = vary_opening(text, rng=rng)
    assert not out.startswith("亲，您好~")
    # 应以变体之一开头
    assert any(out.startswith(v) for v in OPENING_VARIANTS)


def test_vary_opening_no_stale_unchanged():
    text = "嗨~ 这款是爆款"
    assert vary_opening(text) == text


def test_vary_opening_all_stale_handled():
    rng = random.Random(0)
    for stale in STALE_OPENINGS:
        text = stale + " 后续内容"
        out = vary_opening(text, rng=rng)
        assert "后续内容" in out
        assert not out.startswith(stale)


def test_vary_opening_empty():
    assert vary_opening("") == ""


# ─── 疑心检测 ──────────────────────────────────────────────────────────

def test_suspicion_ai_question():
    assert detect_suspicion("你是 AI 吗")
    assert detect_suspicion("你是不是 AI")
    assert detect_suspicion("你是机器人吗？")
    assert detect_suspicion("你是 chatgpt 吗")


def test_suspicion_robot_feeling():
    assert detect_suspicion("感觉你像机器")
    assert detect_suspicion("我怀疑你不是真人")
    assert detect_suspicion("觉得你是 AI")


def test_suspicion_speed_complaint():
    assert detect_suspicion("怎么回这么慢")
    assert detect_suspicion("为啥回这么快")


def test_suspicion_normal_message_no_trigger():
    assert not detect_suspicion("你好 在吗")
    assert not detect_suspicion("这款多少钱")
    assert not detect_suspicion("好的，下单了")


def test_suspicion_empty():
    assert not detect_suspicion("")
    assert not detect_suspicion("   ")


# ─── 综合 humanize ──────────────────────────────────────────────────────

def test_humanize_combines_both():
    text = "亲，您好~ 这款产品的质量好的"
    rng = random.Random(0)
    out = humanize(text, typo_prob=1.0, rng=rng)
    # 开场被替换
    assert not out.startswith("亲，您好~")


def test_humanize_empty():
    assert humanize("") == ""
