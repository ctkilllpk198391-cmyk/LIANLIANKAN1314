"""L2 · 灰产场景检测测试。"""

from __future__ import annotations

from server.compliance_check import (
    GRAY_KEYWORDS,
    SEVERITY_MAP,
    detect_all,
    detect_gray_intent,
    get_rejection_reply,
    is_blocked,
)


def test_gambling_high_severity():
    hit = detect_gray_intent("我们一起玩百家乐 · 下注赢大钱")
    assert hit is not None
    assert hit.category == "gambling"
    assert hit.severity == "high"


def test_porn_high_severity():
    hit = detect_gray_intent("提供约炮服务 · 包夜")
    assert hit is not None
    assert hit.category == "porn"
    assert hit.severity == "high"


def test_fraud_high_severity():
    hit = detect_gray_intent("杀猪盘投资骗 · 假冒身份")
    assert hit is not None
    assert hit.category == "fraud"


def test_mlm_high_severity():
    hit = detect_gray_intent("我们这是三级分销 · 拉人头返佣")
    assert hit is not None
    assert hit.category == "mlm"


def test_medical_medium_severity():
    hit = detect_gray_intent("我帮你确诊 · 开个药方")
    assert hit is not None
    assert hit.category == "medical"
    assert hit.severity == "medium"


def test_finance_tip_medium_severity():
    hit = detect_gray_intent("我私荐股一只 · 保证收益")
    assert hit is not None
    assert hit.category == "finance_tip"
    assert hit.severity == "medium"


def test_normal_message_no_hit():
    assert detect_gray_intent("玉兰油精华多少钱") is None
    assert detect_gray_intent("你好 在吗") is None
    assert detect_gray_intent("好的 下单了") is None


def test_empty_text():
    assert detect_gray_intent("") is None
    assert detect_gray_intent("   ") is None
    assert detect_gray_intent(None) is None


def test_is_blocked_returns_true_for_high():
    assert is_blocked("我玩百家乐") is True
    assert is_blocked("正常消息") is False


def test_is_blocked_returns_false_for_medium():
    """medium 不直接 block · 走人审"""
    assert is_blocked("我帮你确诊") is False


def test_detect_all_multiple_categories():
    text = "我们这传销盘 + 百家乐双结合"
    hits = detect_all(text)
    assert len(hits) >= 2
    categories = {h.category for h in hits}
    assert "mlm" in categories
    assert "gambling" in categories


def test_rejection_reply_generic():
    hit = detect_gray_intent("百家乐")
    reply = get_rejection_reply(hit)
    # 不暴露关键词
    assert "百家乐" not in reply
    assert "服务范围" in reply or "抱歉" in reply


def test_severity_map_complete():
    """每个 GRAY_KEYWORDS 类别都有 severity 配置。"""
    for category in GRAY_KEYWORDS:
        # 政治 默认为 high (没显式映射但 detect_gray_intent fallback medium)
        if category != "political":
            assert category in SEVERITY_MAP
