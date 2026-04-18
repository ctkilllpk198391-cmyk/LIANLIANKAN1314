"""F4 · 跟进序列引擎 · 老板睡觉 AI 自动催 · 4 种 task_type。

task_type:
  - unpaid_30min        客户下单未付款 · 30 分钟后催
  - paid_1day           客户付款 · 1 天后问收到
  - satisfaction_7d     7 天后问满意度
  - repurchase_30d      30 天后推复购

调度：APScheduler 每分钟调 tick() · 扫到点的 pending → 调 sender 推送 → 标 sent。

集成：
  - main.py /v1/inbound 末尾：order intent → schedule unpaid_30min
  - 客户付款回执时：调 schedule paid_1day + satisfaction_7d + repurchase_30d
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import FollowUpTask

logger = logging.getLogger(__name__)


TYPE_DELAYS = {
    "unpaid_30min":   30 * 60,
    "paid_1day":      86400,
    "satisfaction_7d": 7 * 86400,
    "repurchase_30d": 30 * 86400,
}


TEMPLATES = {
    "unpaid_30min":    "亲，刚才那个订单看您还没付款～有什么疑问可以问我哦",
    "paid_1day":       "亲，包裹到了么？有任何问题随时找我～",
    "satisfaction_7d": "您好，上次的产品用了一周感觉怎么样呀？",
    "repurchase_30d":  "好久不见～我们这边新到了一批，您之前买的那款现在有 9 折哦",
}


@dataclass
class ScheduledTask:
    task_id: str
    tenant_id: str
    chat_id: str
    sender_name: str
    task_type: str
    scheduled_at: int
    template_text: str


# 真发送回调（main.py 注入 · 走 ws_pusher / sender）
SendCallback = Callable[[str, str, str, str], Awaitable[bool]]
# (tenant_id, chat_id, text, task_id) → success


class FollowUpEngine:
    """跟进序列调度 + 触发执行。"""

    def __init__(self, send_callback: Optional[SendCallback] = None):
        self.send_callback = send_callback

    async def schedule(
        self,
        tenant_id: str,
        chat_id: str,
        task_type: str,
        sender_name: str = "",
        context: Optional[dict] = None,
        custom_template: Optional[str] = None,
    ) -> str:
        if task_type not in TYPE_DELAYS:
            raise ValueError(f"unknown task_type: {task_type}")

        now = int(time.time())
        scheduled_at = now + TYPE_DELAYS[task_type]
        task_id = f"fu_{uuid.uuid4().hex[:16]}"

        async with session_scope() as session:
            session.add(
                FollowUpTask(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    chat_id=chat_id,
                    sender_name=sender_name or "",
                    task_type=task_type,
                    scheduled_at=scheduled_at,
                    status="pending",
                    template_id=custom_template or task_type,
                    context_json=json.dumps(context or {}, ensure_ascii=False),
                    created_at=now,
                )
            )

        logger.info(
            "follow_up scheduled tenant=%s chat=%s type=%s at=%d",
            tenant_id, chat_id, task_type, scheduled_at,
        )
        return task_id

    async def cancel(self, task_id: str) -> bool:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(FollowUpTask).where(FollowUpTask.task_id == task_id)
                )
            ).scalar_one_or_none()
            if not row or row.status != "pending":
                return False
            row.status = "cancelled"
            return True

    async def list_for_tenant(
        self,
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        async with session_scope() as session:
            stmt = select(FollowUpTask).where(FollowUpTask.tenant_id == tenant_id)
            if status:
                stmt = stmt.where(FollowUpTask.status == status)
            stmt = stmt.order_by(FollowUpTask.scheduled_at.asc()).limit(limit)
            rows = (await session.execute(stmt)).scalars().all()
            return [
                {
                    "task_id": r.task_id,
                    "chat_id": r.chat_id,
                    "sender_name": r.sender_name,
                    "task_type": r.task_type,
                    "scheduled_at": r.scheduled_at,
                    "status": r.status,
                    "template_id": r.template_id,
                    "created_at": r.created_at,
                    "sent_at": r.sent_at,
                }
                for r in rows
            ]

    async def tick(self) -> int:
        """APScheduler 每分钟调 · 返回触发数量。"""
        now = int(time.time())
        due_tasks: list[ScheduledTask] = []

        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(FollowUpTask)
                    .where(FollowUpTask.status == "pending")
                    .where(FollowUpTask.scheduled_at <= now)
                    .limit(100)
                )
            ).scalars().all()

            for r in rows:
                template = TEMPLATES.get(r.template_id or r.task_type, "")
                due_tasks.append(
                    ScheduledTask(
                        task_id=r.task_id,
                        tenant_id=r.tenant_id,
                        chat_id=r.chat_id,
                        sender_name=r.sender_name or "",
                        task_type=r.task_type,
                        scheduled_at=r.scheduled_at,
                        template_text=template,
                    )
                )
                # 乐观标 sent · 失败再回 failed
                r.status = "sent"
                r.sent_at = now

        if not due_tasks:
            return 0

        for task in due_tasks:
            success = False
            if self.send_callback:
                try:
                    success = await self.send_callback(
                        task.tenant_id, task.chat_id, task.template_text, task.task_id
                    )
                except Exception as e:
                    logger.error("follow_up send failed task=%s: %s", task.task_id, e)
                    success = False
            else:
                logger.info(
                    "[follow_up MOCK] tenant=%s chat=%s type=%s text=%s",
                    task.tenant_id, task.chat_id, task.task_type, task.template_text,
                )
                success = True

            if not success:
                async with session_scope() as session:
                    row = (
                        await session.execute(
                            select(FollowUpTask).where(FollowUpTask.task_id == task.task_id)
                        )
                    ).scalar_one_or_none()
                    if row:
                        row.status = "failed"

        return len(due_tasks)

    async def schedule_after_order(
        self,
        tenant_id: str,
        chat_id: str,
        sender_name: str = "",
    ) -> list[str]:
        """订单识别后 · 一次性安排 4 步跟进。"""
        ids = []
        for task_type in ("unpaid_30min", "paid_1day", "satisfaction_7d", "repurchase_30d"):
            ids.append(
                await self.schedule(tenant_id, chat_id, task_type, sender_name=sender_name)
            )
        return ids
