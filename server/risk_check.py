"""服务端风控 · 禁用词 + 7 天滑窗去重。"""

from __future__ import annotations

import time
from difflib import SequenceMatcher

from sqlalchemy import select

from server.db import session_scope
from server.models import Suggestion as SuggestionModel
from shared.const import DEDUP_THRESHOLD, DEDUP_WINDOW_DAYS, FORBIDDEN_WORDS


def contains_forbidden_word(text: str) -> tuple[bool, list[str]]:
    """检查文本是否含禁用词。返回 (命中, 命中词列表)。"""
    hits = [w for w in FORBIDDEN_WORDS if w in text]
    return bool(hits), hits


def text_similarity(a: str, b: str) -> float:
    """0-1 的相似度 · SequenceMatcher 兜底实现。Phase 3 升级 SimHash。"""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


async def is_duplicate(text: str, tenant_id: str, threshold: float = DEDUP_THRESHOLD) -> bool:
    """7 天滑窗内是否有相似度 > threshold 的历史 suggestion。"""
    cutoff = int(time.time()) - DEDUP_WINDOW_DAYS * 86400
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(SuggestionModel.text)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(SuggestionModel.generated_at >= cutoff)
                .order_by(SuggestionModel.generated_at.desc())
                .limit(200)
            )
        ).scalars().all()
    for past in rows:
        if text_similarity(text, past) >= threshold:
            return True
    return False
