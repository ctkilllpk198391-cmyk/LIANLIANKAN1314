"""C2 · 训练数据队列 · 替代 industry_flywheel。

每次老板的审核决策（accept/edit/reject）→ 写入 training_queue 表。
Phase 2 LoRA 训练触发时通过 export() 全量导出 jsonl 喂给 LLaMA-Factory。

权重设计：
  accept → 1.0   （正样本 · 100% 信任）
  edit   → 0.7   （半正样本 · 用 edited_text · 部分信任）
  reject → -0.5  （负样本 · 用 ai_reply 标记为"不要这样回"）
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import TrainingQueue
from shared.proto import IntentResult, ReviewDecision, Suggestion
from shared.types import ReviewDecisionEnum

logger = logging.getLogger(__name__)


WEIGHTS = {
    ReviewDecisionEnum.ACCEPT: 1.0,
    ReviewDecisionEnum.EDIT: 0.7,
    ReviewDecisionEnum.REJECT: -0.5,
}


@dataclass
class TrainingSample:
    customer_msg: str
    ai_reply: str
    final_text: str
    decision: str
    intent: Optional[str]
    emotion: Optional[str]
    weight: float


class TrainingQueueEngine:
    """append-only 队列 · 不修改、不删除（除非 export 后归档）。"""

    async def append(
        self,
        tenant_id: str,
        customer_msg: str,
        suggestion: Suggestion,
        decision: ReviewDecision,
    ) -> int:
        """记录一条训练样本 · 返回 row_id。"""
        weight = WEIGHTS.get(decision.decision, 0.0)
        if decision.decision == ReviewDecisionEnum.EDIT and decision.edited_text:
            final_text = decision.edited_text
        else:
            final_text = suggestion.text

        async with session_scope() as session:
            row = TrainingQueue(
                tenant_id=tenant_id,
                customer_msg=customer_msg,
                ai_reply=suggestion.text,
                final_text=final_text,
                decision=decision.decision.value,
                intent=suggestion.intent.intent.value,
                emotion=suggestion.intent.emotion.value,
                weight=weight,
                created_at=int(time.time()),
            )
            session.add(row)
            await session.flush()
            return row.id

    async def append_auto_sent(
        self,
        tenant_id: str,
        customer_msg: str,
        suggestion: Suggestion,
    ) -> int:
        """全自动发送的也入队 · weight=0.5（弱正样本 · 客户没复负则继续算正）。"""
        async with session_scope() as session:
            row = TrainingQueue(
                tenant_id=tenant_id,
                customer_msg=customer_msg,
                ai_reply=suggestion.text,
                final_text=suggestion.text,
                decision="auto_sent",
                intent=suggestion.intent.intent.value,
                emotion=suggestion.intent.emotion.value,
                weight=0.5,
                created_at=int(time.time()),
            )
            session.add(row)
            await session.flush()
            return row.id

    async def export(
        self,
        tenant_id: str,
        output_path: Path,
        since: Optional[int] = None,
        min_weight: float = 0.0,
    ) -> int:
        """导出 jsonl 给 LLaMA-Factory · 返回写入条数。"""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        async with session_scope() as session:
            stmt = select(TrainingQueue).where(TrainingQueue.tenant_id == tenant_id)
            if since:
                stmt = stmt.where(TrainingQueue.created_at >= since)
            stmt = stmt.where(TrainingQueue.weight >= min_weight)
            rows = (await session.execute(stmt)).scalars().all()

        n = 0
        with open(output_path, "w", encoding="utf-8") as f:
            for row in rows:
                obj = {
                    "instruction": "",
                    "input": row.customer_msg,
                    "output": row.final_text,
                    "weight": row.weight,
                    "metadata": {
                        "intent": row.intent,
                        "emotion": row.emotion,
                        "decision": row.decision,
                        "created_at": row.created_at,
                    },
                }
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                n += 1

        logger.info("exported %d training samples for tenant=%s → %s", n, tenant_id, output_path)
        return n

    async def stats(self, tenant_id: str) -> dict:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(TrainingQueue).where(TrainingQueue.tenant_id == tenant_id)
                )
            ).scalars().all()

        by_decision: dict[str, int] = {}
        total_weight = 0.0
        for r in rows:
            by_decision[r.decision] = by_decision.get(r.decision, 0) + 1
            total_weight += r.weight

        return {
            "total_samples": len(rows),
            "by_decision": by_decision,
            "total_weight": round(total_weight, 2),
            "avg_weight": round(total_weight / len(rows), 3) if rows else 0.0,
        }
