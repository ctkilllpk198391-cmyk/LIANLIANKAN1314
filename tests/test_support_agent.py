"""support.ai_agent 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from support.ai_agent import CustomerSupportAgent, FAQMatcher

FAQ_PATH = Path(__file__).resolve().parent.parent / "support" / "faq.json"


def test_match_install():
    matcher = FAQMatcher(FAQ_PATH)
    res = matcher.match("我怎么安装？")
    assert res is not None
    assert res.intent_id == "install"


def test_match_ban():
    matcher = FAQMatcher(FAQ_PATH)
    res = matcher.match("我账号被封了")
    assert res is not None
    assert res.intent_id == "ban"


def test_match_pricing():
    matcher = FAQMatcher(FAQ_PATH)
    res = matcher.match("多少钱啊")
    assert res is not None
    assert res.intent_id == "pricing"


def test_unknown_question_low_confidence():
    matcher = FAQMatcher(FAQ_PATH)
    res = matcher.match("你妈贵姓")
    # 完全不匹配 → None
    assert res is None or res.confidence < 0.5


def test_agent_auto_reply():
    agent = CustomerSupportAgent(FAQ_PATH)
    out = agent.reply("怎么安装？")
    assert out["type"] == "auto"
    assert out["intent_id"] == "install"


def test_agent_escalates_unknown():
    agent = CustomerSupportAgent(FAQ_PATH)
    out = agent.reply("天上有几颗星星？")
    assert out["type"] == "escalate"
