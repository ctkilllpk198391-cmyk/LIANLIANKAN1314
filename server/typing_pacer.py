"""S1 · 节奏拟人引擎 · 把"机器人 0.5 秒回"变"真人 1-3 秒打字"。

第一性原理：真人不秒回 · 看到 → 想 → 慢慢打字 → 发出。
关键算法：
  - 高斯分布算 typing_delay（按消息长度缩放 μ）
  - 长句多消息分段（split_messages）· 段间 0.8-1.5s
  - 夜间模式：00:00-07:00 客户消息 → 回"刚醒看到~ 早上联系您" 不熬夜
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

# 算法参数（可被 tenant config 覆盖）
DEFAULT_BASE_MS = 1500          # 基础延迟
DEFAULT_PER_CHAR_MS = 50        # 每字 +50ms
DEFAULT_SIGMA_RATIO = 0.3       # σ = 0.3 * μ
MIN_DELAY_MS = 800
MAX_DELAY_MS = 8000

INTER_SEGMENT_MIN_MS = 800
INTER_SEGMENT_MAX_MS = 1500


def compute_typing_delay(
    text: str,
    base_ms: int = DEFAULT_BASE_MS,
    per_char_ms: int = DEFAULT_PER_CHAR_MS,
    sigma_ratio: float = DEFAULT_SIGMA_RATIO,
    rng: random.Random | None = None,
) -> int:
    """高斯分布算延迟 · 按字数缩放 μ。"""
    rng = rng or random
    n = len(text or "")
    mu = base_ms + n * per_char_ms
    sigma = max(1, int(mu * sigma_ratio))
    delay = int(rng.gauss(mu, sigma))
    return max(MIN_DELAY_MS, min(MAX_DELAY_MS, delay))


def compute_inter_segment_delay(rng: random.Random | None = None) -> int:
    """两段消息间隔 · 800-1500ms 均匀分布。"""
    rng = rng or random
    return rng.randint(INTER_SEGMENT_MIN_MS, INTER_SEGMENT_MAX_MS)


def is_nighttime(now_ts: int | None = None, start_hour: int = 0, end_hour: int = 7) -> bool:
    """00:00-07:00 视为夜间 · 不熬夜回。"""
    now_ts = now_ts or int(time.time())
    h = time.localtime(now_ts).tm_hour
    return start_hour <= h < end_hour


NIGHT_REPLY_TEMPLATES = [
    "亲~ 刚醒看到 早上回您可以吗？",
    "稍等 我刚醒~ 早上联系您",
    "现在凌晨啦~ 早上 9 点回您可以吗？",
]


def night_reply(rng: random.Random | None = None) -> str:
    """夜间默认回复（不真处理客户问题 · 让真人早上接管）。"""
    rng = rng or random
    return rng.choice(NIGHT_REPLY_TEMPLATES)


@dataclass
class PacedSegment:
    text: str
    delay_ms: int


def pace_segments(
    segments: list[str],
    base_ms: int = DEFAULT_BASE_MS,
    per_char_ms: int = DEFAULT_PER_CHAR_MS,
    rng: random.Random | None = None,
) -> list[PacedSegment]:
    """给一组消息片段附上每段 typing_delay。

    第一段 delay = 完整 typing_delay
    后续段 delay = inter_segment + typing_delay(本段)
    """
    rng = rng or random
    out: list[PacedSegment] = []
    for i, seg in enumerate(segments):
        if i == 0:
            d = compute_typing_delay(seg, base_ms, per_char_ms, rng=rng)
        else:
            d = compute_inter_segment_delay(rng) + compute_typing_delay(
                seg, base_ms, per_char_ms, rng=rng
            )
        out.append(PacedSegment(text=seg, delay_ms=d))
    return out
