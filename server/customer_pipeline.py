"""T3 · 待成交客户 Pipeline · 从 customer_profiles 表算出高意向客户列表。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy import select

from server.db import session_scope
from server.models import CustomerProfile as CustomerProfileModel

logger = logging.getLogger(__name__)

# 过滤条件常量
_PIPELINE_TIERS = ("A", "B")
_PIPELINE_INTENTS = ("inquiry", "negotiation", "order")
_PIPELINE_MAX_DAYS = 30


def _calc_urgency(last_intent: str | None, days_since_last: int) -> int:
    """urgency 0-3 计算规则：
    - last_intent='order' AND days_since_last >= 1 → 3
    - last_intent='negotiation' AND days_since_last >= 1 → 2
    - last_intent='inquiry' AND days_since_last >= 2 → 1
    - else → 0
    """
    if last_intent == "order" and days_since_last >= 1:
        return 3
    if last_intent == "negotiation" and days_since_last >= 1:
        return 2
    if last_intent == "inquiry" and days_since_last >= 2:
        return 1
    return 0


@dataclass
class PipelineCustomer:
    chat_id: str
    nickname: str
    vip_tier: str          # A/B/C
    stage: str             # explore/compare/near/post_buy/dormant
    last_message_at: int
    days_since_last: int
    last_intent: str
    last_emotion: str
    urgency: int           # 0-3 (⚡ 数量)
    pending_value_estimate: float


class CustomerPipelineBuilder:
    """从 customer_profiles 表算待成交客户。"""

    async def build(self, tenant_id: str, max_count: int = 10) -> list[PipelineCustomer]:
        """过滤：vip_tier in (A,B) AND days_since_last < 30 AND last_intent in (inquiry,negotiation,order)
        排序：urgency desc, days_since_last desc
        """
        now = int(time.time())
        cutoff = now - _PIPELINE_MAX_DAYS * 86400  # 30 天前时间戳

        async with session_scope() as session:
            rows = (await session.execute(
                select(CustomerProfileModel)
                .where(CustomerProfileModel.tenant_id == tenant_id)
                .where(CustomerProfileModel.vip_tier.in_(_PIPELINE_TIERS))
                .where(CustomerProfileModel.last_message_at >= cutoff)
                .where(CustomerProfileModel.last_intent.in_(_PIPELINE_INTENTS))
            )).scalars().all()

        result: list[PipelineCustomer] = []
        for row in rows:
            last_at = row.last_message_at or 0
            days = max(0, int((now - last_at) / 86400)) if last_at else _PIPELINE_MAX_DAYS

            urgency = _calc_urgency(row.last_intent, days)

            result.append(PipelineCustomer(
                chat_id=row.chat_id,
                nickname=row.nickname or "",
                vip_tier=row.vip_tier or "C",
                stage=_infer_stage(row.last_intent),
                last_message_at=last_at,
                days_since_last=days,
                last_intent=row.last_intent or "",
                last_emotion=row.last_emotion or "",
                urgency=urgency,
                pending_value_estimate=_estimate_value(row.vip_tier, row.last_intent),
            ))

        # 排序：urgency desc, days_since_last desc
        result.sort(key=lambda c: (-c.urgency, -c.days_since_last))
        return result[:max_count]


def _infer_stage(last_intent: str | None) -> str:
    """根据 last_intent 推断 pipeline stage。"""
    mapping = {
        "inquiry": "explore",
        "negotiation": "compare",
        "order": "near",
        "repurchase": "post_buy",
    }
    return mapping.get(last_intent or "", "explore")


def _estimate_value(vip_tier: str | None, last_intent: str | None) -> float:
    """简单估值：A 客户 × 1000 · B × 500 · 订单意图 × 2。"""
    base = {"A": 1000.0, "B": 500.0}.get(vip_tier or "C", 200.0)
    multiplier = 2.0 if last_intent == "order" else 1.0
    return base * multiplier
