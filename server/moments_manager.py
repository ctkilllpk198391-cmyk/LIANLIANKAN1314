"""S8 · 朋友圈托管 · AI 写文案 + 定时发。

功能：
  - generate_post(tenant_id, post_type, context)  → 调 LLM 生成文案（≤200 字）
  - schedule_daily(tenant_id)                     → 每天 09/14/19 各 1 条 · 类型轮换
  - list_posts(tenant_id, status, limit)          → 查询 moments_posts
  - cancel(post_id)                               → 取消 scheduled/draft 状态
  - publish(post_id)                              → 标记已发布 · ws push 给 client.sender
  - tick()                                        → APScheduler 每小时调 · 扫到点 → publish

post_type:
  product   / feedback / promo / lifestyle

状态流：
  draft → scheduled → published
               ↓
           cancelled
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Callable, Awaitable, Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import MomentsPost

logger = logging.getLogger(__name__)

# 每天定时发布的小时点
_DAILY_HOURS = (9, 14, 19)

# 按顺序轮换的 post_type（3 条对应 3 个时间点）
_ROTATION = ("product", "feedback", "lifestyle")

# post_type → next_type（循环）
_NEXT_TYPE = {
    "product": "feedback",
    "feedback": "promo",
    "promo": "lifestyle",
    "lifestyle": "product",
}

# ws push 回调类型：(tenant_id, payload_dict) → None
WsPushCallback = Callable[[str, dict], Awaitable[None]]


class MomentsManager:
    """朋友圈托管引擎。"""

    POST_PROMPTS = {
        "product":   "晒今天的爆款 · 200 字内 · 客户视角 · 加 1-2 句行动号召（不直说「快买」）",
        "feedback":  "晒一条客户反馈 · 真情实感 · 200 字内 · 不假",
        "promo":     "限时活动 · 截止时间 + 优惠内容明确 · 不夸张 · 200 字内",
        "lifestyle": "老板的日常 · 喝咖啡/旅行/看书 · 真人感 · 100 字内",
    }

    def __init__(
        self,
        llm_client=None,
        llm_route: str = "doubao_15pro",
        ws_push: Optional[WsPushCallback] = None,
    ):
        self._llm = llm_client
        self._llm_route = llm_route
        self._ws_push = ws_push

    # ── 生成文案 ────────────────────────────────────────────────────────────

    async def generate_post(
        self,
        tenant_id: str,
        post_type: str,
        context: Optional[str] = None,
    ) -> str:
        """调 LLM 生成朋友圈文案（≤200 字）。"""
        if post_type not in self.POST_PROMPTS:
            raise ValueError(f"unknown post_type: {post_type!r}. 合法值: {list(self.POST_PROMPTS)}")

        prompt_hint = self.POST_PROMPTS[post_type]
        user_prompt = prompt_hint
        if context:
            user_prompt = f"{prompt_hint}\n背景：{context}"

        system = (
            "你是微商老板的朋友圈文案助理。"
            "写出真实、自然、有温度的朋友圈内容。"
            "禁止绝对承诺词（保证/一定/稳赚/100%）。"
            "字数严格控制在 200 字以内。"
        )

        if self._llm is None:
            # 无 llm_client 时走 mock
            return f"[mock {post_type}] {prompt_hint[:40]}..."

        try:
            text = await self._llm.respond(
                prompt=user_prompt,
                tenant_id=tenant_id,
                model_route=self._llm_route,
                max_tokens=300,
                system=system,
            )
        except Exception as e:
            logger.warning("moments generate_post llm failed: %s", e)
            text = f"[fallback {post_type}] 今日好物安利~"

        # 截断到 200 字
        if len(text) > 200:
            text = text[:200]
        return text

    # ── 入库 draft ──────────────────────────────────────────────────────────

    async def _save_post(
        self,
        tenant_id: str,
        post_type: str,
        content: str,
        status: str = "draft",
        scheduled_at: Optional[int] = None,
    ) -> str:
        post_id = f"mp_{uuid.uuid4().hex[:16]}"
        now = int(time.time())
        async with session_scope() as session:
            session.add(
                MomentsPost(
                    post_id=post_id,
                    tenant_id=tenant_id,
                    post_type=post_type,
                    content=content,
                    status=status,
                    scheduled_at=scheduled_at,
                    created_at=now,
                )
            )
        logger.info(
            "moments post saved post_id=%s tenant=%s type=%s status=%s",
            post_id, tenant_id, post_type, status,
        )
        return post_id

    # ── 每天安排 3 条 ────────────────────────────────────────────────────────

    async def schedule_daily(self, tenant_id: str) -> list[str]:
        """生成并安排今天 09/14/19 各 1 条 · 类型轮换 · 返回 post_id 列表。"""
        now = int(time.time())
        # 取今天零点（本地时间）
        lt = time.localtime(now)
        today_midnight = int(time.mktime(
            time.struct_time((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, lt.tm_wday, lt.tm_yday, lt.tm_isdst))
        ))

        post_types = _ROTATION  # (product, feedback, lifestyle)
        ids: list[str] = []

        for hour, post_type in zip(_DAILY_HOURS, post_types):
            scheduled_ts = today_midnight + hour * 3600
            content = await self.generate_post(tenant_id, post_type)
            pid = await self._save_post(
                tenant_id=tenant_id,
                post_type=post_type,
                content=content,
                status="scheduled",
                scheduled_at=scheduled_ts,
            )
            ids.append(pid)

        return ids

    # ── 列表查询 ─────────────────────────────────────────────────────────────

    async def list_posts(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[dict]:
        async with session_scope() as session:
            stmt = select(MomentsPost).where(MomentsPost.tenant_id == tenant_id)
            if status:
                stmt = stmt.where(MomentsPost.status == status)
            stmt = stmt.order_by(MomentsPost.created_at.desc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "post_id": r.post_id,
                    "tenant_id": r.tenant_id,
                    "post_type": r.post_type,
                    "content": r.content,
                    "image_urls": json.loads(r.image_urls) if r.image_urls else [],
                    "status": r.status,
                    "scheduled_at": r.scheduled_at,
                    "published_at": r.published_at,
                    "created_at": r.created_at,
                }
                for r in rows
            ]

    # ── 取消 ─────────────────────────────────────────────────────────────────

    async def cancel(self, post_id: str) -> bool:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(MomentsPost).where(MomentsPost.post_id == post_id)
                )
            ).scalar_one_or_none()
            if row is None or row.status not in ("draft", "scheduled"):
                return False
            row.status = "cancelled"
            return True

    # ── 发布 ─────────────────────────────────────────────────────────────────

    async def publish(self, post_id: str) -> bool:
        """标记发布 · 通过 ws push 给 client.sender 实际发送。"""
        now = int(time.time())
        tenant_id: Optional[str] = None
        content: Optional[str] = None
        post_type: Optional[str] = None

        async with session_scope() as session:
            row = (
                await session.execute(
                    select(MomentsPost).where(MomentsPost.post_id == post_id)
                )
            ).scalar_one_or_none()
            if row is None or row.status not in ("draft", "scheduled"):
                return False
            row.status = "published"
            row.published_at = now
            tenant_id = row.tenant_id
            content = row.content
            post_type = row.post_type

        # ws push 通知 client.sender 发朋友圈
        if self._ws_push and tenant_id and content:
            try:
                await self._ws_push(tenant_id, {
                    "type": "moments_post_command",
                    "post_id": post_id,
                    "tenant_id": tenant_id,
                    "post_type": post_type,
                    "content": content,
                    "issued_at": now,
                })
            except Exception as e:
                logger.error("moments ws push failed post_id=%s: %s", post_id, e)

        logger.info("moments post published post_id=%s tenant=%s", post_id, tenant_id)
        return True

    # ── tick（APScheduler 每小时） ────────────────────────────────────────────

    async def tick(self) -> int:
        """扫到点的 scheduled posts → 调 publish 流程。返回触发数量。"""
        now = int(time.time())
        due_ids: list[str] = []

        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(MomentsPost)
                    .where(MomentsPost.status == "scheduled")
                    .where(MomentsPost.scheduled_at <= now)
                    .limit(50)
                )
            ).scalars().all()
            due_ids = [r.post_id for r in rows]

        if not due_ids:
            return 0

        count = 0
        for pid in due_ids:
            ok = await self.publish(pid)
            if ok:
                count += 1

        if count:
            logger.info("moments tick fired %d posts", count)
        return count
