"""F2 · 客户档案引擎 · 每个 contact 一份动态档案。

第一性原理：让 AI 像老板的助理一样"记住每个客户"。
- get_or_create:  inbound 流程入口 · 不存在则建空档案
- update_after_inbound: 客户消息后增量更新（last_intent/emotion/message_at/total）
- update_after_send: 老板审核后增量（accepted_replies + purchase_history）
- render_for_prompt: 拼成 prompt 用的"已知信息"块
- compute_vip_tier: A（VIP · 月成交≥3）/ B（活跃 · 月对话≥5）/ C（其他）
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import CustomerProfile as CustomerProfileModel
from shared.proto import InboundMsg, IntentResult, ReviewDecision, Suggestion
from shared.types import EmotionEnum, IntentEnum, ReviewDecisionEnum

logger = logging.getLogger(__name__)

# T4 · 加密开关（默认 false · 测试不挂 · prod 设 BAIYANG_ENCRYPTION_ENABLED=1 启用）
_ENCRYPTION_ENABLED: bool = os.environ.get("BAIYANG_ENCRYPTION_ENABLED", "").lower() in ("1", "true", "yes")


def _get_kms_lazy():
    """懒加载 KMS 单例 · 避免 import 时触发 cryptography 错误。"""
    from server.encryption import get_default_kms  # noqa: PLC0415
    return get_default_kms()


def _encrypt_sensitive(snapshot_dict: dict, tenant_id: str) -> dict:
    """把 sensitive_topics / notes 加密（JSON str · 存 DB）。
    仅在 BAIYANG_ENCRYPTION_ENABLED=1 时生效。返回修改后的 dict copy。
    """
    if not _ENCRYPTION_ENABLED:
        return snapshot_dict
    kms = _get_kms_lazy()
    result = dict(snapshot_dict)
    if "sensitive_topics" in result and result["sensitive_topics"]:
        raw = json.dumps(result["sensitive_topics"], ensure_ascii=False)
        result["sensitive_topics"] = kms.encrypt_str(tenant_id, raw)
    if "notes" in result and result["notes"]:
        result["notes"] = kms.encrypt_str(tenant_id, result["notes"])
    return result


def _decrypt_sensitive(snapshot: "CustomerProfileSnapshot") -> "CustomerProfileSnapshot":
    """解密 sensitive_topics / notes · 返回解密后的新 snapshot。
    仅在 BAIYANG_ENCRYPTION_ENABLED=1 时生效。
    """
    if not _ENCRYPTION_ENABLED:
        return snapshot
    kms = _get_kms_lazy()
    tenant_id = snapshot.tenant_id

    sensitive_topics = snapshot.sensitive_topics
    notes = snapshot.notes

    # sensitive_topics 加密后存为 JSON str（非 list）
    if isinstance(sensitive_topics, str) and sensitive_topics:
        try:
            decrypted = kms.decrypt_str(tenant_id, sensitive_topics)
            sensitive_topics = json.loads(decrypted)
        except Exception:
            logger.warning("_decrypt_sensitive: sensitive_topics 解密失败 · 返回空列表")
            sensitive_topics = []

    if isinstance(notes, str) and notes:
        try:
            notes = kms.decrypt_str(tenant_id, notes)
        except Exception:
            logger.warning("_decrypt_sensitive: notes 解密失败 · 返回空字符串")
            notes = ""

    # 返回同类型 snapshot（用 dataclasses replace 等价）
    from dataclasses import replace  # noqa: PLC0415
    return replace(snapshot, sensitive_topics=sensitive_topics, notes=notes)


@dataclass
class CustomerProfileSnapshot:
    """轻量内存快照 · 给 prompt_builder 用。"""

    tenant_id: str
    chat_id: str
    nickname: str
    preferred_addressing: str
    vip_tier: str
    purchase_history: list[dict]
    sensitive_topics: list[str]
    tags: list[str]
    last_intent: Optional[str]
    last_emotion: Optional[str]
    last_message_at: Optional[int]
    total_messages: int
    accepted_replies: int
    notes: str

    @property
    def is_returning(self) -> bool:
        return self.total_messages > 1

    @property
    def days_since_last(self) -> Optional[int]:
        if not self.last_message_at:
            return None
        return int((time.time() - self.last_message_at) / 86400)


class CustomerProfileEngine:
    """5 个核心方法 · 全异步 · 每次访问 DB · 上层不缓存（避免一致性问题）。"""

    async def get_or_create(
        self,
        tenant_id: str,
        chat_id: str,
        sender_name: str = "",
    ) -> CustomerProfileSnapshot:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(CustomerProfileModel)
                    .where(CustomerProfileModel.tenant_id == tenant_id)
                    .where(CustomerProfileModel.chat_id == chat_id)
                )
            ).scalar_one_or_none()

            if row is None:
                row = CustomerProfileModel(
                    tenant_id=tenant_id,
                    chat_id=chat_id,
                    nickname=sender_name or "",
                    preferred_addressing="",
                    vip_tier="C",
                    purchase_history="[]",
                    sensitive_topics="[]",
                    tags="[]",
                    last_message_at=int(time.time()),
                    total_messages=0,
                    accepted_replies=0,
                    notes="",
                    updated_at=int(time.time()),
                )
                session.add(row)
                await session.flush()

            return self._to_snapshot(row)

    async def update_after_inbound(
        self,
        tenant_id: str,
        chat_id: str,
        msg: InboundMsg,
        intent: IntentResult,
    ) -> None:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(CustomerProfileModel)
                    .where(CustomerProfileModel.tenant_id == tenant_id)
                    .where(CustomerProfileModel.chat_id == chat_id)
                )
            ).scalar_one_or_none()

            if row is None:
                logger.warning("update_after_inbound: profile missing %s/%s", tenant_id, chat_id)
                return

            row.total_messages = (row.total_messages or 0) + 1
            row.last_intent = intent.intent.value
            row.last_emotion = intent.emotion.value
            row.last_message_at = msg.timestamp
            if msg.sender_name and not row.nickname:
                row.nickname = msg.sender_name
            row.updated_at = int(time.time())

    async def update_after_send(
        self,
        tenant_id: str,
        chat_id: str,
        suggestion: Suggestion,
        decision: ReviewDecision,
        order_amount: float = 0.0,
        sku: Optional[str] = None,
    ) -> None:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(CustomerProfileModel)
                    .where(CustomerProfileModel.tenant_id == tenant_id)
                    .where(CustomerProfileModel.chat_id == chat_id)
                )
            ).scalar_one_or_none()

            if row is None:
                return

            if decision.decision == ReviewDecisionEnum.ACCEPT:
                row.accepted_replies = (row.accepted_replies or 0) + 1

            if order_amount > 0:
                history = json.loads(row.purchase_history or "[]")
                history.append({
                    "date": int(time.time()),
                    "sku": sku or "unknown",
                    "amount": order_amount,
                })
                row.purchase_history = json.dumps(history, ensure_ascii=False)
                row.vip_tier = self.compute_vip_tier_from_history(history)

            # T4 · 敏感字段落盘前加密
            if _ENCRYPTION_ENABLED and row.notes:
                try:
                    kms = _get_kms_lazy()
                    row.notes = kms.encrypt_str(tenant_id, row.notes)
                except Exception:
                    logger.warning("update_after_send: notes 加密失败 · 明文存储")

            row.updated_at = int(time.time())

    @staticmethod
    def render_for_prompt(snapshot: CustomerProfileSnapshot) -> str:
        """生成可塞 system prompt 的"已知信息"块。读取前先解密敏感字段。"""
        if snapshot.total_messages == 0:
            return ""  # 全新客户 · 不污染 prompt
        snapshot = _decrypt_sensitive(snapshot)

        lines = ["【客户档案】"]
        if snapshot.nickname:
            tier_label = {"A": "VIP-A", "B": "活跃-B", "C": "新客-C"}.get(snapshot.vip_tier, "C")
            lines.append(f"- 称呼：{snapshot.nickname}（{tier_label}）")
        if snapshot.preferred_addressing:
            lines.append(f"- 偏好称谓：{snapshot.preferred_addressing}")
        if snapshot.purchase_history:
            recent = snapshot.purchase_history[-3:]
            for item in recent:
                date_str = time.strftime("%Y-%m", time.localtime(item.get("date", 0)))
                amt = item.get("amount", 0)
                sku = item.get("sku", "")
                lines.append(f"- 历史购买：{date_str} · {sku} · ¥{amt:.0f}")
        if snapshot.sensitive_topics:
            lines.append(f"- 敏感点：{', '.join(snapshot.sensitive_topics)}")
        if snapshot.tags:
            lines.append(f"- 标签：{', '.join(snapshot.tags)}")
        if snapshot.notes:
            lines.append(f"- 备注：{snapshot.notes}")
        if snapshot.is_returning and snapshot.days_since_last is not None:
            if snapshot.days_since_last == 0:
                lines.append("- 提醒：今天已联系过 · 不要重复打招呼")
            elif snapshot.days_since_last <= 7:
                lines.append(f"- 提醒：{snapshot.days_since_last} 天前刚联系过")
            elif snapshot.days_since_last >= 30:
                lines.append(f"- 提醒：已 {snapshot.days_since_last} 天未联系 · 适合主动关怀")

        return "\n".join(lines)

    @staticmethod
    def compute_vip_tier_from_history(history: list[dict]) -> str:
        """A 月成交≥3 · B 月成交≥1 · C 其他。"""
        now = time.time()
        month_ago = now - 30 * 86400
        recent = [h for h in history if h.get("date", 0) >= month_ago]
        if len(recent) >= 3:
            return "A"
        if len(recent) >= 1:
            return "B"
        return "C"

    @staticmethod
    def compute_vip_tier(snapshot: CustomerProfileSnapshot) -> str:
        """B 月对话≥5 也算活跃（即使没成交）。"""
        if snapshot.purchase_history:
            tier = CustomerProfileEngine.compute_vip_tier_from_history(snapshot.purchase_history)
            if tier in ("A", "B"):
                return tier
        if snapshot.total_messages >= 5 and snapshot.days_since_last is not None and snapshot.days_since_last <= 30:
            return "B"
        return "C"

    @staticmethod
    def _to_snapshot(row: CustomerProfileModel) -> CustomerProfileSnapshot:
        return CustomerProfileSnapshot(
            tenant_id=row.tenant_id,
            chat_id=row.chat_id,
            nickname=row.nickname or "",
            preferred_addressing=row.preferred_addressing or "",
            vip_tier=row.vip_tier or "C",
            purchase_history=json.loads(row.purchase_history or "[]"),
            sensitive_topics=json.loads(row.sensitive_topics or "[]"),
            tags=json.loads(row.tags or "[]"),
            last_intent=row.last_intent,
            last_emotion=row.last_emotion,
            last_message_at=row.last_message_at,
            total_messages=row.total_messages or 0,
            accepted_replies=row.accepted_replies or 0,
            notes=row.notes or "",
        )
