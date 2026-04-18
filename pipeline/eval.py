"""LoRA 训练效果评估 · 采纳率 / 风格匹配 / 安全。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

logger = logging.getLogger(__name__)


@dataclass
class EvalSample:
    customer_msg: str
    boss_real_reply: str
    ai_generated: str
    intent: str
    risk: str


@dataclass
class EvalReport:
    n_samples: int
    avg_acceptance_score: float  # 主观打分（0-1）
    style_match_rate: float       # 与老板真实风格相似度
    forbidden_word_violation_rate: float
    over_length_rate: float
    intent_distribution: dict[str, int]


class ReplyEvaluator:
    """Phase 1 提供接口骨架，Phase 2 接 judge LLM。"""

    def __init__(self, judge_mode: str = "rule"):
        self.judge_mode = judge_mode

    def evaluate(self, samples: Sequence[EvalSample]) -> EvalReport:
        from shared.const import FORBIDDEN_WORDS, MAX_REPLY_LENGTH

        if not samples:
            return EvalReport(0, 0.0, 0.0, 0.0, 0.0, {})

        from server.risk_check import text_similarity

        n = len(samples)
        sim_scores = [text_similarity(s.boss_real_reply, s.ai_generated) for s in samples]
        forbidden_hits = sum(
            1 for s in samples if any(w in s.ai_generated for w in FORBIDDEN_WORDS)
        )
        over_length = sum(1 for s in samples if len(s.ai_generated) > MAX_REPLY_LENGTH)

        intents: dict[str, int] = {}
        for s in samples:
            intents[s.intent] = intents.get(s.intent, 0) + 1

        return EvalReport(
            n_samples=n,
            avg_acceptance_score=sum(sim_scores) / n,
            style_match_rate=sum(1 for s in sim_scores if s >= 0.5) / n,
            forbidden_word_violation_rate=forbidden_hits / n,
            over_length_rate=over_length / n,
            intent_distribution=intents,
        )
