"""S1 · 节奏拟人引擎测试。"""

from __future__ import annotations

import random
import time

from server.typing_pacer import (
    MAX_DELAY_MS,
    MIN_DELAY_MS,
    NIGHT_REPLY_TEMPLATES,
    compute_inter_segment_delay,
    compute_typing_delay,
    is_nighttime,
    night_reply,
    pace_segments,
)


def test_short_text_within_bounds():
    rng = random.Random(42)
    delay = compute_typing_delay("在的~", rng=rng)
    assert MIN_DELAY_MS <= delay <= MAX_DELAY_MS


def test_long_text_larger_delay_on_average():
    rng_short = random.Random(42)
    rng_long = random.Random(42)
    short_delays = [compute_typing_delay("好的", rng=rng_short) for _ in range(20)]
    long_delays = [compute_typing_delay("亲" * 100, rng=rng_long) for _ in range(20)]
    assert sum(long_delays) / 20 > sum(short_delays) / 20


def test_delay_clamped_min():
    delay = compute_typing_delay("", base_ms=10)
    assert delay >= MIN_DELAY_MS


def test_delay_clamped_max():
    delay = compute_typing_delay("a" * 1000, base_ms=10000, per_char_ms=1000)
    assert delay <= MAX_DELAY_MS


def test_inter_segment_delay_in_range():
    rng = random.Random(0)
    for _ in range(50):
        d = compute_inter_segment_delay(rng=rng)
        assert 800 <= d <= 1500


def test_nighttime_detection():
    # 02:00 → 夜间
    night_ts = int(time.mktime((2026, 4, 16, 2, 0, 0, 0, 0, -1)))
    assert is_nighttime(night_ts) is True
    # 14:00 → 白天
    day_ts = int(time.mktime((2026, 4, 16, 14, 0, 0, 0, 0, -1)))
    assert is_nighttime(day_ts) is False
    # 06:59 → 夜间
    edge = int(time.mktime((2026, 4, 16, 6, 59, 0, 0, 0, -1)))
    assert is_nighttime(edge) is True
    # 07:00 → 白天
    edge2 = int(time.mktime((2026, 4, 16, 7, 0, 0, 0, 0, -1)))
    assert is_nighttime(edge2) is False


def test_night_reply_in_pool():
    rng = random.Random(0)
    reply = night_reply(rng=rng)
    assert reply in NIGHT_REPLY_TEMPLATES


def test_pace_segments_assigns_delays():
    rng = random.Random(7)
    segs = pace_segments(["在的~", "这款是爆款~", "你想要啥色号？"], rng=rng)
    assert len(segs) == 3
    for s in segs:
        assert MIN_DELAY_MS <= s.delay_ms <= MAX_DELAY_MS + 1500
    # 后续段比第一段总时间长（含 inter_segment）
    assert segs[1].delay_ms > MIN_DELAY_MS


def test_pace_empty_list():
    assert pace_segments([]) == []


def test_pace_single_segment():
    rng = random.Random(0)
    out = pace_segments(["好的"], rng=rng)
    assert len(out) == 1
