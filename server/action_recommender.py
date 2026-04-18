"""T3 · 行动推荐引擎 · 规则引擎为每个客户产出下一步最优行动。"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import CustomerProfile as CustomerProfileModel

logger = logging.getLogger(__name__)

# 推荐阈值常量
_CARE_DAYS = 30        # days_since_last >= 30 → care
_FOLLOW_UP_DAYS = 1    # inquiry 后 >= 1 天 → follow_up
_UPSELL_DAYS = 7       # A 客户 >= 7 天 → upsell (requirements 要求 7 天)
_REPURCHASE_WINDOWS = (30, 60, 90)  # 购买后 x 天 ± 3 天视为复购窗口


@dataclass
class RecommendedAction:
    chat_id: str
    nickname: str
    action_type: str       # care/follow_up/handoff/upsell/repurchase
    reason: str
    suggested_text: str
    confidence: float


# ── 话术模板 ─────────────────────────────────────────────────────────────────

_TEMPLATES: dict[str, str] = {
    "handoff":    "您好，感谢您的反馈！我们非常重视您的问题，专属客服即将为您服务，请稍候。",
    "care":       "您好 {nickname}，好久不见！最近有什么需要可以随时联系我～",
    "follow_up":  "您好 {nickname}，之前您咨询过的问题，请问还有什么疑问吗？随时告诉我！",
    "upsell":     "您好 {nickname}，我们最近有几款新品特别适合您，感兴趣的话我给您介绍一下？",
    "repurchase": "您好 {nickname}，距离上次购买已有一段时间了，需要补货的话可以告诉我～",
}


def _render_template(action_type: str, nickname: str) -> str:
    tpl = _TEMPLATES.get(action_type, "您好，请问有什么可以帮您？")
    return tpl.replace("{nickname}", nickname or "您")


def _last_purchase_days(purchase_history_json: str | None) -> Optional[int]:
    """返回距最后一次购买的天数 · 无记录返回 None。"""
    if not purchase_history_json:
        return None
    try:
        history = json.loads(purchase_history_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not history:
        return None
    last_date = max((h.get("date", 0) for h in history), default=0)
    if not last_date:
        return None
    return max(0, int((time.time() - last_date) / 86400))


def _in_repurchase_window(purchase_days: int, window: int, tolerance: int = 3) -> bool:
    return abs(purchase_days - window) <= tolerance


class ActionRecommender:
    """规则引擎 · 优先级顺序产出推荐行动。"""

    async def recommend_for_customer(
        self,
        profile: CustomerProfileModel,
    ) -> Optional[RecommendedAction]:
        """规则引擎按优先级返回 1 个 action 或 None：
        1. last_intent='complaint' → handoff（人工接管）
        2. days_since_last >= 30 → care（主动关怀）
        3. last_intent='inquiry' AND days_since_last >= 1 → follow_up（催）
        4. has_purchase AND days_since_last_purchase ≈ 30/60/90 → repurchase
        5. vip_tier='A' AND days_since_last >= 7 → upsell
        """
        now = int(time.time())
        nickname = profile.nickname or ""
        last_at = profile.last_message_at or 0
        days_since_last = max(0, int((now - last_at) / 86400)) if last_at else 999
        last_intent = profile.last_intent or ""
        vip_tier = profile.vip_tier or "C"

        # 规则 1：投诉 → 人工接管
        if last_intent == "complaint":
            return RecommendedAction(
                chat_id=profile.chat_id,
                nickname=nickname,
                action_type="handoff",
                reason="客户有投诉未解决，建议人工接管",
                suggested_text=_render_template("handoff", nickname),
                confidence=0.95,
            )

        # 规则 2：沉睡 30 天 → 主动关怀
        if days_since_last >= _CARE_DAYS:
            return RecommendedAction(
                chat_id=profile.chat_id,
                nickname=nickname,
                action_type="care",
                reason=f"已 {days_since_last} 天未联系，建议主动关怀",
                suggested_text=_render_template("care", nickname),
                confidence=0.85,
            )

        # 规则 3：询价后 >= 1 天无跟进 → follow_up
        if last_intent == "inquiry" and days_since_last >= _FOLLOW_UP_DAYS:
            return RecommendedAction(
                chat_id=profile.chat_id,
                nickname=nickname,
                action_type="follow_up",
                reason=f"询价后 {days_since_last} 天未跟进，建议催一下",
                suggested_text=_render_template("follow_up", nickname),
                confidence=0.80,
            )

        # 规则 4：复购窗口（30/60/90 天）
        purchase_days = _last_purchase_days(profile.purchase_history)
        if purchase_days is not None:
            for window in _REPURCHASE_WINDOWS:
                if _in_repurchase_window(purchase_days, window):
                    return RecommendedAction(
                        chat_id=profile.chat_id,
                        nickname=nickname,
                        action_type="repurchase",
                        reason=f"距上次购买约 {purchase_days} 天，建议推复购",
                        suggested_text=_render_template("repurchase", nickname),
                        confidence=0.75,
                    )

        # 规则 5：A 客户 >= 7 天 → upsell
        if vip_tier == "A" and days_since_last >= _UPSELL_DAYS:
            return RecommendedAction(
                chat_id=profile.chat_id,
                nickname=nickname,
                action_type="upsell",
                reason=f"VIP-A 客户 {days_since_last} 天未联系，建议推升级",
                suggested_text=_render_template("upsell", nickname),
                confidence=0.70,
            )

        return None

    async def recommend_top_n(
        self,
        tenant_id: str,
        n: int = 10,
    ) -> list[RecommendedAction]:
        """扫所有 customer_profiles · 返回 top N 推荐。"""
        async with session_scope() as session:
            rows = (await session.execute(
                select(CustomerProfileModel)
                .where(CustomerProfileModel.tenant_id == tenant_id)
            )).scalars().all()

        results: list[RecommendedAction] = []
        for row in rows:
            action = await self.recommend_for_customer(row)
            if action is not None:
                results.append(action)

        # 按 confidence 降序，取 top N
        results.sort(key=lambda a: -a.confidence)
        return results[:n]
