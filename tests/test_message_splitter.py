"""S1 · 长消息拆段测试。"""

from __future__ import annotations

from server.message_splitter import split_messages


def test_short_text_not_split():
    text = "在的亲~"
    assert split_messages(text) == ["在的亲~"]


def test_empty_returns_empty():
    assert split_messages("") == []
    assert split_messages("   ") == []


def test_explicit_newline_split():
    text = "在的~\n这款是爆款\n你要啥色号？"
    out = split_messages(text)
    assert len(out) == 3
    assert "在的~" in out[0]
    assert "色号" in out[2]


def test_long_text_split_by_sentence():
    text = "亲，你好呀。这款产品是我们家的爆款，质量非常好。今天下单还送赠品哦！"
    out = split_messages(text, max_per_msg=20)
    assert len(out) >= 2
    assert all(len(s) <= 30 for s in out)  # 略超允许（保完整句）


def test_max_segments_capped():
    text = "句一。句二。句三。句四。句五。句六。句七。"
    out = split_messages(text, max_per_msg=10, max_segments=3)
    assert len(out) <= 3


def test_no_punctuation_keeps_one_segment():
    text = "短消息"
    assert split_messages(text) == ["短消息"]


def test_mixed_chinese_english_punct():
    text = "Hi there! 这款 30ml 装的精华呢. 适合 25 岁以上哦~"
    out = split_messages(text, max_per_msg=20)
    assert len(out) >= 2


def test_returns_no_empty_segments():
    text = "句一。\n\n\n句二。"
    out = split_messages(text)
    assert all(s.strip() for s in out)
