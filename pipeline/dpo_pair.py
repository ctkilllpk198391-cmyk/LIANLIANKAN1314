"""DPO 配对生成器 · accept = chosen, rewrite = rejected。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import select

from server.db import session_scope
from server.models import Review as ReviewModel
from server.models import Suggestion as SuggestionModel

logger = logging.getLogger(__name__)


async def export_dpo_pairs(tenant_id: str, output_path: Path, limit: int = 5000) -> int:
    """从 reviews 导出 (chosen, rejected) 对给 DPO 训练。

    chosen = accepted suggestion text 或 edited_text
    rejected = same inbound 上一个 rewrite 失败的版本（如有）

    Phase 1 简化版：accepted 与 rejected 配对挑选不同 inbound 的回复
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pairs = []
    async with session_scope() as session:
        rows = (
            await session.execute(
                select(SuggestionModel, ReviewModel)
                .join(ReviewModel, ReviewModel.msg_id == SuggestionModel.msg_id)
                .where(SuggestionModel.tenant_id == tenant_id)
                .limit(limit)
            )
        ).all()

        accepted = [(s, r) for s, r in rows if r.decision == "accept"]
        rejected = [(s, r) for s, r in rows if r.decision == "reject"]

        for i, (sug_a, _) in enumerate(accepted):
            if i >= len(rejected):
                break
            sug_r, _ = rejected[i]
            pairs.append(
                {
                    "prompt": "（待补 prompt context）",
                    "chosen": sug_a.text,
                    "rejected": sug_r.text,
                }
            )

    with output_path.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")

    logger.info("exported %d DPO pairs → %s", len(pairs), output_path)
    return len(pairs)
