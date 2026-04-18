"""T2 · 营销方案生成器 · 基于上传资料 → 朋友圈+私聊SOP+群发 一套搞定。

老板把"双11预热.txt"丢进魔法文件夹（T1）→ 自动 generate → 老板审核 → activate：
  - 朋友圈 5 条 → 进 moments_posts
  - 私聊 SOP → 写进 customer_profile.notes / tenant.fact
  - 群发 → 进 follow_up_tasks（按 vip_tier 分组）
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import FollowUpTask, MarketingPlan, MomentsPost

logger = logging.getLogger(__name__)


# ─── 数据契约 ────────────────────────────────────────────────────────────

@dataclass
class MomentPostDraft:
    day_offset: int           # -7 / -3 / 0 / +3 / +7
    angle: str                # 悬念/种草/开抢/复盘
    content: str
    suggested_image: str = ""


@dataclass
class PrivateChatSOP:
    trigger: str              # "客户问活动" / "客户犹豫"
    reply_template: str       # 含变量 {customer_name}


@dataclass
class GroupBroadcast:
    target_tier: str          # A/B/C/all
    text: str
    suggested_send_at: int = 0


@dataclass
class MarketingPlanData:
    plan_id: str
    tenant_id: str
    source_content_id: Optional[str]
    moments_posts: list[MomentPostDraft] = field(default_factory=list)
    private_sops: list[PrivateChatSOP] = field(default_factory=list)
    group_broadcasts: list[GroupBroadcast] = field(default_factory=list)
    estimated_impact: dict = field(default_factory=dict)
    status: str = "draft"
    created_at: int = 0


# ─── 生成器 ──────────────────────────────────────────────────────────────

class MarketingPlanGenerator:
    """LLM 驱动 · 基于资料 + 老板风格 + 行业 + 心理学触发器 生成完整方案。"""

    PROMPT_TEMPLATE = """你是顶级营销策划。基于以下资料 · 生成一套微信营销方案。

# 资料内容
{content}

# 老板信息
- 名字：{boss_name}
- 风格：{style_hints}
- 行业：{industry}

# 输出要求（严格 JSON · 不要解释 · 不要前缀）：
{{
  "moments_posts": [
    {{"day_offset": -3, "angle": "悬念", "content": "≤150 字 · 真人感 · 1-2 emoji", "suggested_image": "图片描述"}},
    {{"day_offset": 0, "angle": "种草", "content": "...", "suggested_image": "..."}},
    {{"day_offset": 0, "angle": "开抢", "content": "...", "suggested_image": "..."}},
    {{"day_offset": 1, "angle": "晒单", "content": "...", "suggested_image": "..."}},
    {{"day_offset": 3, "angle": "复盘", "content": "...", "suggested_image": "..."}}
  ],
  "private_sops": [
    {{"trigger": "客户问活动", "reply_template": "..."}},
    {{"trigger": "客户犹豫", "reply_template": "..."}},
    {{"trigger": "客户砍价", "reply_template": "..."}},
    {{"trigger": "客户下单", "reply_template": "..."}},
    {{"trigger": "客户售后", "reply_template": "..."}}
  ],
  "group_broadcasts": [
    {{"target_tier": "A", "text": "VIP 专属话术..."}},
    {{"target_tier": "B", "text": "活跃客户话术..."}},
    {{"target_tier": "C", "text": "新客户话术..."}}
  ],
  "estimated_impact": {{"expected_orders": 12, "expected_revenue": 3580}}
}}
"""

    def __init__(self, llm_client=None, llm_route: str = "doubao_15pro", tenants=None):
        self.llm = llm_client
        self.llm_route = llm_route
        self.tenants = tenants

    async def generate(
        self,
        tenant_id: str,
        source_content_id: Optional[str] = None,
        source_text: str = "",
        boss_name: str = "老板",
        style_hints: str = "",
        industry: str = "通用",
    ) -> str:
        """生成营销方案 · 入库 status='draft' · 返回 plan_id。"""
        # 用 tenant 配置覆盖默认（如有）
        if self.tenants and self.tenants.has(tenant_id):
            cfg = self.tenants.get(tenant_id)
            boss_name = boss_name or cfg.boss_name
            style_hints = style_hints or cfg.style_hints
            industry = industry or getattr(cfg, "industry", "通用")

        plan_data = await self._call_llm_or_fallback(
            tenant_id=tenant_id,
            source_content_id=source_content_id,
            content=source_text,
            boss_name=boss_name,
            style_hints=style_hints,
            industry=industry,
        )

        plan_id = plan_data.plan_id
        async with session_scope() as session:
            session.add(
                MarketingPlan(
                    plan_id=plan_id,
                    tenant_id=tenant_id,
                    source_content_id=source_content_id,
                    payload_json=json.dumps(_serialize_plan(plan_data), ensure_ascii=False),
                    status="draft",
                    created_at=plan_data.created_at,
                )
            )

        logger.info("marketing_plan generated tenant=%s plan_id=%s", tenant_id, plan_id)
        return plan_id

    async def _call_llm_or_fallback(
        self,
        tenant_id: str,
        source_content_id: Optional[str],
        content: str,
        boss_name: str,
        style_hints: str,
        industry: str,
    ) -> MarketingPlanData:
        plan_id = f"mp_{uuid.uuid4().hex[:16]}"
        now = int(time.time())

        # 没 LLM · 兜底用模板
        if self.llm is None:
            return self._fallback(plan_id, tenant_id, source_content_id, content, now)

        prompt = self.PROMPT_TEMPLATE.format(
            content=(content or "")[:2000],
            boss_name=boss_name,
            style_hints=style_hints or "直接简洁",
            industry=industry,
        )
        try:
            raw = await self.llm.respond(
                prompt=prompt,
                tenant_id=tenant_id,
                model_route=self.llm_route,
                max_tokens=2000,
                system="你是顶级微信营销策划。严格按 JSON schema 输出。",
            )
            parsed = _extract_json(raw)
            if parsed:
                return _parse_plan(plan_id, tenant_id, source_content_id, now, parsed)
        except Exception as e:
            logger.warning("marketing LLM call failed · fallback: %s", e)

        return self._fallback(plan_id, tenant_id, source_content_id, content, now)

    @staticmethod
    def _fallback(plan_id, tenant_id, source_content_id, content, now) -> MarketingPlanData:
        excerpt = (content or "新方案")[:50]
        return MarketingPlanData(
            plan_id=plan_id,
            tenant_id=tenant_id,
            source_content_id=source_content_id,
            moments_posts=[
                MomentPostDraft(day_offset=-3, angle="悬念", content=f"快了快了~ 这次的{excerpt}你们要爱死我"),
                MomentPostDraft(day_offset=0, angle="开抢", content=f"上新啦！{excerpt} 限时 24h 优惠"),
                MomentPostDraft(day_offset=1, angle="晒单", content=f"今天又出 X 单 · 谢谢宝宝们的支持"),
            ],
            private_sops=[
                PrivateChatSOP(trigger="客户问活动", reply_template="亲~ 这次活动只到今晚 12 点 · 错过等明年"),
                PrivateChatSOP(trigger="客户砍价", reply_template="VIP 价已经是底了亲 · 今天下单加送小样"),
            ],
            group_broadcasts=[
                GroupBroadcast(target_tier="A", text="VIP 专属：今晚 8 点开抢 · 提前预定锁库存"),
                GroupBroadcast(target_tier="B", text="新品上线 · 老顾客 9 折"),
                GroupBroadcast(target_tier="C", text="新人福利 · 首单减 ¥30"),
            ],
            estimated_impact={"expected_orders": 8, "expected_revenue": 2400},
            created_at=now,
        )


# ─── Activator · draft → 落到各模块 ──────────────────────────────────────

class MarketingPlanActivator:
    """activate 后：朋友圈进 moments_posts · 群发进 follow_up_tasks · SOP 写 tenant.fact。"""

    async def activate(self, plan_id: str) -> dict:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(MarketingPlan).where(MarketingPlan.plan_id == plan_id)
                )
            ).scalar_one_or_none()
            if not row:
                return {"ok": False, "reason": "not found"}
            if row.status == "active":
                return {"ok": False, "reason": "already active"}

            payload = json.loads(row.payload_json or "{}")
            tenant_id = row.tenant_id

        moments_count = await self._activate_moments(tenant_id, payload.get("moments_posts", []), plan_id)
        broadcast_count = await self._activate_broadcasts(tenant_id, payload.get("group_broadcasts", []))

        async with session_scope() as session:
            row = (
                await session.execute(
                    select(MarketingPlan).where(MarketingPlan.plan_id == plan_id)
                )
            ).scalar_one_or_none()
            if row:
                row.status = "active"
                row.activated_at = int(time.time())

        return {
            "ok": True,
            "plan_id": plan_id,
            "moments_scheduled": moments_count,
            "broadcasts_scheduled": broadcast_count,
        }

    @staticmethod
    async def _activate_moments(tenant_id: str, moments: list[dict], plan_id: str) -> int:
        """把 moments_posts draft 入 moments_posts 表 (status=scheduled)。"""
        now = int(time.time())
        created = 0
        async with session_scope() as session:
            for m in moments:
                day_offset = m.get("day_offset", 0)
                scheduled_at = now + day_offset * 86400
                content = m.get("content", "")
                if not content:
                    continue
                session.add(
                    MomentsPost(
                        post_id=f"mp_{uuid.uuid4().hex[:16]}",
                        tenant_id=tenant_id,
                        post_type=m.get("angle", "promo"),
                        content=content,
                        image_urls=json.dumps([m.get("suggested_image", "")] if m.get("suggested_image") else []),
                        status="scheduled",
                        scheduled_at=scheduled_at,
                        created_at=now,
                    )
                )
                created += 1
        return created

    @staticmethod
    async def _activate_broadcasts(tenant_id: str, broadcasts: list[dict]) -> int:
        """群发文案进 follow_up_tasks · task_type='broadcast_<tier>'。"""
        now = int(time.time())
        created = 0
        async with session_scope() as session:
            for b in broadcasts:
                tier = b.get("target_tier", "all")
                text = b.get("text", "")
                if not text:
                    continue
                send_at = b.get("suggested_send_at") or (now + 3600)
                session.add(
                    FollowUpTask(
                        task_id=f"bc_{uuid.uuid4().hex[:16]}",
                        tenant_id=tenant_id,
                        chat_id=f"_broadcast_{tier}",
                        sender_name="",
                        task_type=f"broadcast_{tier}",
                        scheduled_at=send_at,
                        status="pending",
                        template_id="marketing_broadcast",
                        context_json=json.dumps({"text": text, "tier": tier}, ensure_ascii=False),
                        created_at=now,
                    )
                )
                created += 1
        return created


# ─── 查询 ────────────────────────────────────────────────────────────────

async def list_plans(tenant_id: str, status: Optional[str] = None, limit: int = 50) -> list[dict]:
    async with session_scope() as session:
        stmt = select(MarketingPlan).where(MarketingPlan.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(MarketingPlan.status == status)
        stmt = stmt.order_by(MarketingPlan.created_at.desc()).limit(limit)
        rows = (await session.execute(stmt)).scalars().all()
        return [
            {
                "plan_id": r.plan_id,
                "source_content_id": r.source_content_id,
                "status": r.status,
                "created_at": r.created_at,
                "activated_at": r.activated_at,
                "payload": json.loads(r.payload_json or "{}"),
            }
            for r in rows
        ]


# ─── 工具函数 ────────────────────────────────────────────────────────────

def _serialize_plan(p: MarketingPlanData) -> dict:
    return {
        "moments_posts": [asdict(x) for x in p.moments_posts],
        "private_sops": [asdict(x) for x in p.private_sops],
        "group_broadcasts": [asdict(x) for x in p.group_broadcasts],
        "estimated_impact": p.estimated_impact,
    }


def _extract_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    import re
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _parse_plan(plan_id, tenant_id, source_content_id, now, parsed: dict) -> MarketingPlanData:
    return MarketingPlanData(
        plan_id=plan_id,
        tenant_id=tenant_id,
        source_content_id=source_content_id,
        moments_posts=[MomentPostDraft(**m) for m in parsed.get("moments_posts", []) if isinstance(m, dict)],
        private_sops=[PrivateChatSOP(**s) for s in parsed.get("private_sops", []) if isinstance(s, dict)],
        group_broadcasts=[GroupBroadcast(**b) for b in parsed.get("group_broadcasts", []) if isinstance(b, dict)],
        estimated_impact=parsed.get("estimated_impact", {}),
        created_at=now,
    )
