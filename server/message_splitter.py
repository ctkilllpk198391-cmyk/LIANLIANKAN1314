"""S1 · 长消息拆段 · 把 200 字 reply 拆 2-3 段 · 模仿真人发短消息习惯。

策略：
  1. 优先按 \\n 切（明确换行就是分段意图）
  2. 然后按句子标点切（。！？.!?）
  3. 单段 ≤ max_per_msg（默认 60 字 · 微信常见短信节奏）
  4. 总段数 1-3（不要拆太碎 · 让客户烦）
"""

from __future__ import annotations

import re

DEFAULT_MAX_PER_MSG = 60
MAX_SEGMENTS = 3


def split_messages(
    text: str,
    max_per_msg: int = DEFAULT_MAX_PER_MSG,
    max_segments: int = MAX_SEGMENTS,
) -> list[str]:
    """长 reply → 1-3 段。"""
    if not text or not text.strip():
        return []

    text = text.strip()

    # 1. 按 \n 切（用户明确换行 · 即使总长短也要拆）
    raw_segments = [s.strip() for s in re.split(r"\n+", text) if s.strip()]

    # 短消息且无换行 · 不拆
    if len(raw_segments) == 1 and len(text) <= max_per_msg:
        return [text]

    # 2. 每个 segment 太长就再按句号切
    refined: list[str] = []
    for seg in raw_segments:
        if len(seg) <= max_per_msg:
            refined.append(seg)
        else:
            refined.extend(_split_by_sentence(seg, max_per_msg))

    # 3. 控制总段数：超 max_segments 合并尾部
    if len(refined) > max_segments:
        head = refined[: max_segments - 1]
        tail = " ".join(refined[max_segments - 1 :])
        refined = head + [tail]

    return [s for s in refined if s]


def _split_by_sentence(text: str, max_per_msg: int) -> list[str]:
    """按句子标点切 · 累积到接近 max_per_msg 时断。"""
    sentences = re.split(r"(?<=[。！？!?\.])", text)
    out: list[str] = []
    buf = ""
    for sent in sentences:
        if not sent:
            continue
        if len(buf) + len(sent) <= max_per_msg or not buf:
            buf += sent
        else:
            if buf.strip():
                out.append(buf.strip())
            buf = sent
    if buf.strip():
        out.append(buf.strip())
    return out
