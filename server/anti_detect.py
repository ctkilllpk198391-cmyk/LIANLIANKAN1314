"""S6 · 反检测套件 · 防客户识破是 AI。

3 个工具：
  - inject_typo: 5% 概率插入轻微 typo（"的"→"得" 等同音）
  - vary_opening: 替换"亲，您好~"为 10 个变体
  - detect_suspicion: 客户问"你是 AI 吗" → 立即转人工

集成点：
  - generator.generate 末尾：rewrite 后 → 反检测处理 → 输出
  - main.py inbound：detect_suspicion(client_text) → True → audit + 暂停 + 推老板
"""

from __future__ import annotations

import random
import re
from typing import Optional

# ─── 1. 错别字注入 · 让 reply 不像"机器完美" ────────────────────────────

# 真人最常见的同音/形近字误打
TYPO_MAP = {
    "的": ["得", "地"],
    "得": ["的"],
    "地": ["的"],
    "再": ["在"],
    "在": ["再"],
    "做": ["作"],
    "作": ["做"],
    "他": ["她"],
    "她": ["他"],
    "那": ["哪"],
    "哪": ["那"],
    "象": ["像"],
    "像": ["象"],
}

DEFAULT_TYPO_PROB = 0.05  # 5% 概率单字 typo · 不能太频繁


def inject_typo(text: str, prob: float = DEFAULT_TYPO_PROB, rng: Optional[random.Random] = None) -> str:
    """每个可替换字以 prob 概率替换为同音字。整段最多 1 个 typo（避免假到露馅）。"""
    if not text or prob <= 0:
        return text
    rng = rng or random
    # 只允许整段 1 个 typo · 平均长度 50 字 · 5%×50=2.5 → cap to 1
    candidates = [(i, c) for i, c in enumerate(text) if c in TYPO_MAP]
    if not candidates:
        return text
    if rng.random() > prob * len(candidates):
        return text   # 此次不注入
    idx, char = rng.choice(candidates)
    replacement = rng.choice(TYPO_MAP[char])
    return text[:idx] + replacement + text[idx + 1 :]


# ─── 2. 开场白变体 · 不要永远"亲，您好~" ────────────────────────────────

OPENING_VARIANTS = [
    "嗨~",
    "在的~",
    "在呢亲",
    "刚看到",
    "嗯哼",
    "诶在",
    "看到啦",
    "对的~",
    "好嘞",
    "亲在呢",
]

# 老套开场（要被替换）
STALE_OPENINGS = ["亲，您好~", "亲您好", "您好亲", "您好~", "您好亲~"]


def vary_opening(text: str, rng: Optional[random.Random] = None) -> str:
    """检测到老套开场 → 替换成随机变体。"""
    if not text:
        return text
    rng = rng or random
    for stale in STALE_OPENINGS:
        if text.startswith(stale):
            new = rng.choice(OPENING_VARIANTS)
            return new + text[len(stale):]
    return text


# ─── 3. 疑心检测 · 客户怀疑是 AI → 立即转人工 ───────────────────────────

SUSPICION_PATTERNS = [
    r"你是.*(AI|人工智能|机器人|智能助手|GPT|chatgpt|聊天机器人)",
    r"(像|是).*(机器|程序|脚本|AI)",
    r"(感觉|怀疑|觉得).*(不是真人|是 ?AI|是机器)",
    r"真人.*回.*吗",
    r"机器.*回.*吗",
    r"(为啥|怎么).*回.*(慢|快|那么|这么).*",
    r"复制.*粘贴.*吧",
]

_SUSPICION_REGEX = [re.compile(p, re.IGNORECASE) for p in SUSPICION_PATTERNS]


def detect_suspicion(text: str) -> bool:
    """客户消息含怀疑表达 → True。"""
    if not text or not text.strip():
        return False
    for pattern in _SUSPICION_REGEX:
        if pattern.search(text):
            return True
    return False


# ─── 综合处理 · 给 generator 用 ──────────────────────────────────────────

def humanize(
    text: str,
    typo_prob: float = DEFAULT_TYPO_PROB,
    rng: Optional[random.Random] = None,
) -> str:
    """对 AI 输出做反检测处理 · 一次过。

    顺序：先变开场 → 再 typo（保证开场词不被 typo 污染）。
    """
    if not text:
        return text
    out = vary_opening(text, rng=rng)
    out = inject_typo(out, prob=typo_prob, rng=rng)
    return out
