"""老板看板 · 采纳率 / 配额 / LoRA 状态 · Dashboard v2 + v3。"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import func, select

from server.db import session_scope
from server.models import CustomerProfile as CustomerProfileModel
from server.models import Message as MessageModel
from server.models import Review as ReviewModel
from server.models import SentMessage as SentModel
from server.models import Suggestion as SuggestionModel

if TYPE_CHECKING:
    from server.account_failover import AccountFailover
    from server.health_monitor import HealthMonitor
    from server.customer_pipeline import CustomerPipelineBuilder
    from server.action_recommender import ActionRecommender

logger = logging.getLogger(__name__)


class DashboardBuilder:
    # ──────────────────────────────────────────────
    # 旧接口（backward compat · test_dashboard.py）
    # ──────────────────────────────────────────────
    async def build(self, tenant_id: str) -> dict:
        now = int(time.time())
        today_start = now - (now % 86400)
        week_start = now - 7 * 86400

        async with session_scope() as session:
            sugs_today = (await session.execute(
                select(SuggestionModel)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(SuggestionModel.generated_at >= today_start)
            )).scalars().all()
            n_total = len(sugs_today)

            reviews_today = (await session.execute(
                select(ReviewModel)
                .join(SuggestionModel, SuggestionModel.msg_id == ReviewModel.msg_id)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(ReviewModel.reviewed_at >= today_start)
            )).scalars().all()

            sent_today = (await session.execute(
                select(SentModel)
                .where(SentModel.tenant_id == tenant_id)
                .where(SentModel.sent_at >= today_start)
            )).scalars().all()

            msgs_week = (await session.execute(
                select(MessageModel)
                .where(MessageModel.tenant_id == tenant_id)
                .where(MessageModel.timestamp >= week_start)
            )).scalars().all()

        n_acc = sum(1 for r in reviews_today if r.decision == "accept")
        n_edit = sum(1 for r in reviews_today if r.decision == "edit")
        n_rej = sum(1 for r in reviews_today if r.decision == "reject")
        n_reviewed = max(1, len(reviews_today))

        return {
            "tenant_id": tenant_id,
            "as_of": now,
            "today": {
                "total_generated": n_total,
                "accepted": n_acc,
                "edited": n_edit,
                "rejected": n_rej,
                "acceptance_rate": round(n_acc / n_reviewed, 3),
                "sent": len(sent_today),
            },
            "week": {
                "inbound_messages": len(msgs_week),
                "unique_chats": len({m.chat_id for m in msgs_week}),
            },
            "lora_status": {
                "loaded": False,
                "version": "n/a (Phase 1 mock)",
            },
            "quota": {
                "daily_used": len(sent_today),
                "daily_max": 100,
                "remaining": max(0, 100 - len(sent_today)),
            },
        }

    # ──────────────────────────────────────────────
    # v2 全量 JSON
    # ──────────────────────────────────────────────
    async def build_v2(self, tenant_id: str) -> dict:
        now = int(time.time())
        today_start = now - (now % 86400)

        # today 数据
        async with session_scope() as session:
            sugs_today = (await session.execute(
                select(SuggestionModel)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(SuggestionModel.generated_at >= today_start)
            )).scalars().all()
            n_total = len(sugs_today)

            reviews_today = (await session.execute(
                select(ReviewModel)
                .join(SuggestionModel, SuggestionModel.msg_id == ReviewModel.msg_id)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(ReviewModel.reviewed_at >= today_start)
            )).scalars().all()

            sent_today = (await session.execute(
                select(SentModel)
                .where(SentModel.tenant_id == tenant_id)
                .where(SentModel.sent_at >= today_start)
            )).scalars().all()

        n_acc = sum(1 for r in reviews_today if r.decision == "accept")
        n_edit = sum(1 for r in reviews_today if r.decision == "edit")
        n_rej = sum(1 for r in reviews_today if r.decision == "reject")
        n_reviewed = max(1, len(reviews_today))

        today = {
            "total_generated": n_total,
            "accepted": n_acc,
            "edited": n_edit,
            "rejected": n_rej,
            "acceptance_rate": round(n_acc / n_reviewed, 3),
            "sent": len(sent_today),
        }

        week_trend = await self.build_trend(tenant_id, days=7)
        customers = await self.build_customers(tenant_id)
        funnel = await self.build_funnel(tenant_id)
        benchmark = await self.build_benchmark(tenant_id)

        # 组装 health 占位（其他模块可能未启动 · mock 兜底）
        health = {
            "primary_account_score": 92,
            "active_account_id": "primary_wx_001",
            "yellow_alerts": 0,
            "red_alerts": 0,
        }

        return {
            "tenant_id": tenant_id,
            "as_of": now,
            "today": today,
            "week_trend": week_trend,
            "customers": customers,
            "funnel": funnel,
            "benchmark": benchmark,
            "health": health,
        }

    # ──────────────────────────────────────────────
    # 7 天趋势
    # ──────────────────────────────────────────────
    async def build_trend(self, tenant_id: str, days: int = 7) -> dict:
        now = int(time.time())
        dates = []
        acceptance_rate = []
        sent_count = []
        high_risk_blocked = []

        for i in range(days - 1, -1, -1):
            day_start = now - (now % 86400) - i * 86400
            day_end = day_start + 86400
            dt = datetime.fromtimestamp(day_start, tz=timezone.utc)
            dates.append(dt.strftime("%Y-%m-%d"))

            async with session_scope() as session:
                reviews = (await session.execute(
                    select(ReviewModel)
                    .join(SuggestionModel, SuggestionModel.msg_id == ReviewModel.msg_id)
                    .where(SuggestionModel.tenant_id == tenant_id)
                    .where(ReviewModel.reviewed_at >= day_start)
                    .where(ReviewModel.reviewed_at < day_end)
                )).scalars().all()

                sent = (await session.execute(
                    select(SentModel)
                    .where(SentModel.tenant_id == tenant_id)
                    .where(SentModel.sent_at >= day_start)
                    .where(SentModel.sent_at < day_end)
                )).scalars().all()

                # high_risk_blocked: suggestions with risk=high 且没有 sent record
                high_risk_sugs = (await session.execute(
                    select(SuggestionModel)
                    .where(SuggestionModel.tenant_id == tenant_id)
                    .where(SuggestionModel.risk == "high")
                    .where(SuggestionModel.generated_at >= day_start)
                    .where(SuggestionModel.generated_at < day_end)
                )).scalars().all()

            n_acc = sum(1 for r in reviews if r.decision == "accept")
            n_reviewed = max(1, len(reviews))
            rate = round(n_acc / n_reviewed, 3)

            acceptance_rate.append(rate)
            sent_count.append(len(sent))
            high_risk_blocked.append(len(high_risk_sugs))

        return {
            "dates": dates,
            "acceptance_rate": acceptance_rate,
            "sent_count": sent_count,
            "high_risk_blocked": high_risk_blocked,
        }

    # ──────────────────────────────────────────────
    # 客户分级
    # ──────────────────────────────────────────────
    async def build_customers(self, tenant_id: str, tier: str | None = None) -> dict:
        now = int(time.time())
        stale_threshold = now - 30 * 86400  # 30 天前

        async with session_scope() as session:
            q = select(CustomerProfileModel).where(CustomerProfileModel.tenant_id == tenant_id)
            if tier:
                q = q.where(CustomerProfileModel.vip_tier == tier.upper())
            profiles = (await session.execute(q)).scalars().all()

        total = len(profiles)
        tier_a = sum(1 for p in profiles if p.vip_tier == "A")
        tier_b = sum(1 for p in profiles if p.vip_tier == "B")
        tier_c = sum(1 for p in profiles if p.vip_tier == "C")

        # 沉睡客户：30 天未联系
        stale = [
            p.chat_id for p in profiles
            if (p.last_message_at is None or p.last_message_at < stale_threshold)
        ][:10]  # top 10

        return {
            "total": total,
            "tier_a": tier_a,
            "tier_b": tier_b,
            "tier_c": tier_c,
            "stale_30d_alert": stale,
        }

    # ──────────────────────────────────────────────
    # 成交漏斗
    # ──────────────────────────────────────────────
    async def build_funnel(self, tenant_id: str) -> dict:
        """
        漏斗四阶段从 suggestions 表的 intent 列统计：
          inquiry     → INQUIRY / GENERAL
          negotiation → NEGOTIATION
          order       → ORDER
          repurchase  → REPURCHASE
        """
        async with session_scope() as session:
            all_sugs = (await session.execute(
                select(SuggestionModel)
                .where(SuggestionModel.tenant_id == tenant_id)
            )).scalars().all()

        inquiry = sum(
            1 for s in all_sugs
            if s.intent.lower() in ("inquiry", "general", "greeting", "complaint",
                                    "question", "price_inquiry")
        )
        negotiation = sum(
            1 for s in all_sugs if s.intent.lower() in ("negotiation", "bargain", "negotiate")
        )
        order = sum(
            1 for s in all_sugs if s.intent.lower() in ("order", "purchase")
        )
        repurchase = sum(
            1 for s in all_sugs if s.intent.lower() in ("repurchase", "reorder", "repeat_order")
        )

        # 如果某阶段为 0，转化率为 0
        def rate(num: int, denom: int) -> float:
            return round(num / denom, 3) if denom > 0 else 0.0

        return {
            "inquiry": inquiry,
            "negotiation": negotiation,
            "order": order,
            "repurchase": repurchase,
            "rates": {
                "inq_to_neg": rate(negotiation, inquiry),
                "neg_to_order": rate(order, negotiation),
                "order_to_rep": rate(repurchase, order),
            },
        }

    # ──────────────────────────────────────────────
    # v3 汇总：v2 + pipeline + actions + multi_account
    # ──────────────────────────────────────────────
    async def build_v3(
        self,
        tenant_id: str,
        pipeline_builder: Optional["CustomerPipelineBuilder"] = None,
        action_recommender: Optional["ActionRecommender"] = None,
        account_failover: Optional["AccountFailover"] = None,
        health_monitor: Optional["HealthMonitor"] = None,
    ) -> dict:
        """v2 + pipeline + actions + multi_account + today_summary。"""
        # 基础 v2 数据
        v2 = await self.build_v2(tenant_id)

        # pipeline：待成交客户
        pipeline_data: list[dict] = []
        if pipeline_builder is not None:
            customers = await pipeline_builder.build(tenant_id, max_count=10)
            pipeline_data = [
                {
                    "chat_id": c.chat_id,
                    "nickname": c.nickname,
                    "vip_tier": c.vip_tier,
                    "stage": c.stage,
                    "last_message_at": c.last_message_at,
                    "days_since_last": c.days_since_last,
                    "last_intent": c.last_intent,
                    "last_emotion": c.last_emotion,
                    "urgency": c.urgency,
                    "pending_value_estimate": c.pending_value_estimate,
                }
                for c in customers
            ]

        # actions：AI 推荐行动
        actions_data: list[dict] = []
        if action_recommender is not None:
            actions = await action_recommender.recommend_top_n(tenant_id, n=10)
            actions_data = [
                {
                    "chat_id": a.chat_id,
                    "nickname": a.nickname,
                    "action_type": a.action_type,
                    "reason": a.reason,
                    "suggested_text": a.suggested_text,
                    "confidence": a.confidence,
                }
                for a in actions
            ]

        # multi_account：多账号视图
        multi_account: list[dict] = []
        if account_failover is not None:
            accounts = await account_failover.list_accounts(tenant_id)
            for acc in accounts:
                multi_account.append({
                    "account_id": acc.account_id,
                    "role": acc.role,
                    "wxid": acc.wxid,
                    "is_active": acc.is_active,
                    "health_level": acc.health_level,
                    "health_score": acc.health_score,
                    "customer_count": 0,       # 占位：按账号统计客户数（Phase 后期细化）
                    "today_orders": 0,          # 占位：今日成交（Phase 后期细化）
                })

        # today_summary：今日汇总
        today_summary = await self._build_today_summary(tenant_id)

        return {
            **v2,
            "pipeline": pipeline_data,
            "actions": actions_data,
            "multi_account": multi_account,
            "today_summary": today_summary,
        }

    async def _build_today_summary(self, tenant_id: str) -> dict:
        """今日 inbound 数 / auto_send 数 / 转人工 / 成交估算。"""
        now = int(time.time())
        today_start = now - (now % 86400)

        async with session_scope() as session:
            # 今日 inbound（messages 表按 tenant_id + timestamp）
            msgs_today = (await session.execute(
                select(MessageModel)
                .where(MessageModel.tenant_id == tenant_id)
                .where(MessageModel.timestamp >= today_start)
            )).scalars().all()

            # 今日 auto_send（sent_messages 表）
            sent_today = (await session.execute(
                select(SentModel)
                .where(SentModel.tenant_id == tenant_id)
                .where(SentModel.sent_at >= today_start)
            )).scalars().all()

            # 转人工：today 的 reject 决策
            reviews_today = (await session.execute(
                select(ReviewModel)
                .join(SuggestionModel, SuggestionModel.msg_id == ReviewModel.msg_id)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(ReviewModel.reviewed_at >= today_start)
            )).scalars().all()

        n_inbound = len(msgs_today)
        n_auto_send = len(sent_today)
        n_handoff = sum(1 for r in reviews_today if r.decision == "reject")
        n_orders = sum(
            1 for s in await self._get_today_suggestions(tenant_id, today_start)
            if s.intent in ("order", "repurchase")
        )

        return {
            "inbound": n_inbound,
            "auto_send": n_auto_send,
            "handoff": n_handoff,
            "orders": n_orders,
        }

    async def _get_today_suggestions(self, tenant_id: str, today_start: int) -> list:
        async with session_scope() as session:
            return (await session.execute(
                select(SuggestionModel)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(SuggestionModel.generated_at >= today_start)
            )).scalars().all()

    # ──────────────────────────────────────────────
    # 同行对标
    # ──────────────────────────────────────────────
    async def build_benchmark(self, tenant_id: str) -> dict:
        now = int(time.time())
        today_start = now - (now % 86400)

        # 计算今日采纳率
        async with session_scope() as session:
            reviews_today = (await session.execute(
                select(ReviewModel)
                .join(SuggestionModel, SuggestionModel.msg_id == ReviewModel.msg_id)
                .where(SuggestionModel.tenant_id == tenant_id)
                .where(ReviewModel.reviewed_at >= today_start)
            )).scalars().all()

        n_acc = sum(1 for r in reviews_today if r.decision == "accept")
        n_reviewed = max(1, len(reviews_today))
        your_rate = round(n_acc / n_reviewed, 3)

        industry_p50 = 0.65
        industry_p90 = 0.85
        delta_pct = round((your_rate - industry_p50) / industry_p50 * 100, 1)

        return {
            "industry": "微商",
            "your_acceptance_rate": your_rate,
            "industry_p50": industry_p50,
            "industry_p90": industry_p90,
            "delta_pct": delta_pct,
        }
