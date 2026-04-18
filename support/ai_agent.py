"""AI 客服 · 关键词匹配 + 兜底 LLM。Phase 7 落地。"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class FAQResponse:
    intent_id: str
    answer: str
    confidence: float


class FAQMatcher:
    """轻量关键词匹配 · 命中即答 · 没命中走 LLM。"""

    def __init__(self, faq_path: Path):
        with faq_path.open(encoding="utf-8") as f:
            data = json.load(f)
        self.intents = data["intents"]

    def match(self, user_msg: str) -> Optional[FAQResponse]:
        msg_l = user_msg.lower()
        best: Optional[FAQResponse] = None
        best_hits = 0
        for intent in self.intents:
            hits = sum(1 for kw in intent["keywords"] if kw.lower() in msg_l)
            if hits > best_hits:
                best_hits = hits
                best = FAQResponse(
                    intent_id=intent["id"],
                    answer=intent["answer"],
                    confidence=min(1.0, 0.5 + 0.15 * hits),
                )
        return best


class CustomerSupportAgent:
    """客服 agent · FAQ 优先 · 未命中转人工。"""

    def __init__(self, faq_path: Path, escalate_threshold: float = 0.6):
        self.matcher = FAQMatcher(faq_path)
        self.escalate_threshold = escalate_threshold

    def reply(self, user_msg: str) -> dict:
        match = self.matcher.match(user_msg)
        if not match or match.confidence < self.escalate_threshold:
            return {
                "type": "escalate",
                "answer": "您的问题需要人工处理 · 客服 5 分钟内联系您 · 请稍等 ☕",
                "intent_id": match.intent_id if match else "unknown",
            }
        return {
            "type": "auto",
            "answer": match.answer,
            "intent_id": match.intent_id,
            "confidence": match.confidence,
        }
