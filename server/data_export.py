"""T5 · 数据合规导出 · 仅原始聊天 · 不含训练资产。"""

from __future__ import annotations

import csv
import io
import json
import time

from sqlalchemy import func, select, text

from server.db import session_scope
from server.models import CustomerProfile, Message, SentMessage, Suggestion


class DataExporter:
    """导出 tenant 的原始聊天数据（合规导出，不含训练资产）。"""

    # 导出列定义（CSV 模式）
    _CSV_COLUMNS = [
        "msg_id",
        "chat_id",
        "sender_name",
        "text",
        "sent_text",
        "timestamp",
    ]

    async def export_chats(self, tenant_id: str, format: str = "csv") -> bytes:
        """导出原始 messages + suggestions + sent_messages。

        包含：messages / suggestions / sent_messages
        不包含：customer_profiles / lora / training_queue / knowledge_chunks（训练资产）

        csv 列：msg_id, chat_id, sender_name, text, sent_text, timestamp
        json：完整 dict list
        """
        rows = await self._fetch_rows(tenant_id)

        if format == "json":
            return json.dumps(rows, ensure_ascii=False, indent=2).encode("utf-8")

        # 默认 csv
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self._CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        return buf.getvalue().encode("utf-8")

    async def _fetch_rows(self, tenant_id: str) -> list[dict]:
        """联表查询：messages LEFT JOIN suggestions LEFT JOIN sent_messages。"""
        async with session_scope() as session:
            # 取该 tenant 所有消息
            msg_rows = (
                await session.execute(
                    select(Message).where(Message.tenant_id == tenant_id)
                    .order_by(Message.timestamp.asc())
                )
            ).scalars().all()

            # 取建议（msg_id → text）
            sug_rows = (
                await session.execute(
                    select(Suggestion.inbound_msg_id, Suggestion.msg_id, Suggestion.text)
                    .where(Suggestion.tenant_id == tenant_id)
                )
            ).all()
            sug_map: dict[str, str] = {r.inbound_msg_id: r.text for r in sug_rows}
            sug_id_map: dict[str, str] = {r.inbound_msg_id: r.msg_id for r in sug_rows}

            # 取已发（sug_msg_id → sent_text）
            sent_rows = (
                await session.execute(
                    select(SentMessage.msg_id, SentMessage.text)
                    .where(SentMessage.tenant_id == tenant_id)
                )
            ).all()
            sent_map: dict[str, str] = {r.msg_id: r.text for r in sent_rows}

        result = []
        for msg in msg_rows:
            sug_text = sug_map.get(msg.msg_id, "")
            sug_msg_id = sug_id_map.get(msg.msg_id, "")
            sent_text = sent_map.get(sug_msg_id, "") if sug_msg_id else ""
            result.append({
                "msg_id": msg.msg_id,
                "chat_id": msg.chat_id,
                "sender_name": msg.sender_name or "",
                "text": msg.text,
                "sent_text": sent_text,
                "timestamp": msg.timestamp,
            })
        return result

    async def export_summary(self, tenant_id: str) -> dict:
        """统计信息：消息数 / 客户数 / 已运行天数 / 数据保留天数。"""
        async with session_scope() as session:
            # 消息总数
            msg_count = (
                await session.execute(
                    select(func.count()).select_from(Message)
                    .where(Message.tenant_id == tenant_id)
                )
            ).scalar_one()

            # 客户数（customer_profiles 数量）
            customer_count = (
                await session.execute(
                    select(func.count()).select_from(CustomerProfile)
                    .where(CustomerProfile.tenant_id == tenant_id)
                )
            ).scalar_one()

            # 最早消息时间
            earliest = (
                await session.execute(
                    select(func.min(Message.timestamp))
                    .where(Message.tenant_id == tenant_id)
                )
            ).scalar_one()

        now = int(time.time())
        days_running = max(0, (now - earliest) // 86400) if earliest else 0

        return {
            "tenant_id": tenant_id,
            "message_count": msg_count,
            "customer_count": customer_count,
            "days_running": days_running,
            "data_retention_days": 30,   # grace period
            "exported_at": now,
        }
