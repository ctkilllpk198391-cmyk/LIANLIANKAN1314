"""T5 · 数据导出测试 · ≥4 用例。"""

from __future__ import annotations

import csv
import io
import json
import time

import pytest

from server.data_export import DataExporter
from server.db import session_scope
from server.models import Message, SentMessage, Suggestion


# ─── 辅助：插入测试数据 ──────────────────────────────────────────────────────

async def _seed_messages(tenant_id: str, count: int = 3) -> list[str]:
    """插入 count 条消息，返回 msg_id 列表。"""
    ids = []
    async with session_scope() as session:
        for i in range(count):
            msg_id = f"msg_{tenant_id}_{i}"
            session.add(Message(
                msg_id=msg_id,
                tenant_id=tenant_id,
                chat_id=f"chat_{i}",
                sender_id=f"user_{i}",
                sender_name=f"客户{i}",
                text=f"你好，第{i}条消息",
                msg_type="text",
                timestamp=int(time.time()) + i,
            ))
            ids.append(msg_id)
    return ids


async def _seed_suggestions(tenant_id: str, msg_ids: list[str]) -> list[str]:
    """为每条消息插入一条建议，返回 sug_id 列表。"""
    sug_ids = []
    async with session_scope() as session:
        for i, inbound_id in enumerate(msg_ids):
            sug_id = f"sug_{tenant_id}_{i}"
            session.add(Suggestion(
                msg_id=sug_id,
                tenant_id=tenant_id,
                inbound_msg_id=inbound_id,
                intent="greeting",
                risk="low",
                text=f"您好，这是第{i}条回复",
                model_route="mock",
                generated_at=int(time.time()) + i,
            ))
            sug_ids.append(sug_id)
    return sug_ids


async def _seed_sent(tenant_id: str, sug_ids: list[str]) -> None:
    """为部分建议插入已发记录。"""
    async with session_scope() as session:
        for i, sug_id in enumerate(sug_ids[:2]):  # 只发前两条
            session.add(SentMessage(
                msg_id=sug_id,
                tenant_id=tenant_id,
                chat_id=f"chat_{i}",
                text=f"已发：第{i}条",
                sent_at=int(time.time()) + i,
                success=1,
            ))


# ─── 测试 ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_export_csv_returns_bytes(temp_db):
    """export_chats csv 返回 bytes 且包含 CSV header。"""
    await _seed_messages("tenant_0001", count=2)
    exporter = DataExporter()
    data = await exporter.export_chats("tenant_0001", format="csv")
    assert isinstance(data, bytes)
    text = data.decode("utf-8")
    assert "msg_id" in text
    assert "chat_id" in text
    assert "sender_name" in text
    assert "timestamp" in text


@pytest.mark.asyncio
async def test_export_csv_columns_correct(temp_db):
    """CSV 导出包含正确的 6 列。"""
    await _seed_messages("tenant_0001", count=1)
    exporter = DataExporter()
    data = await exporter.export_chats("tenant_0001", format="csv")
    reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
    expected_cols = {"msg_id", "chat_id", "sender_name", "text", "sent_text", "timestamp"}
    assert expected_cols.issubset(set(reader.fieldnames or []))


@pytest.mark.asyncio
async def test_export_json_returns_list(temp_db):
    """export_chats json 返回有效 JSON list。"""
    msg_ids = await _seed_messages("tenant_0001", count=3)
    await _seed_suggestions("tenant_0001", msg_ids)
    exporter = DataExporter()
    data = await exporter.export_chats("tenant_0001", format="json")
    result = json.loads(data.decode("utf-8"))
    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0]["msg_id"].startswith("msg_")


@pytest.mark.asyncio
async def test_export_sent_text_joined(temp_db):
    """sent_text 字段正确 join 到对应消息行。"""
    msg_ids = await _seed_messages("tenant_0001", count=3)
    sug_ids = await _seed_suggestions("tenant_0001", msg_ids)
    await _seed_sent("tenant_0001", sug_ids)

    exporter = DataExporter()
    data = await exporter.export_chats("tenant_0001", format="json")
    rows = json.loads(data.decode("utf-8"))

    # 前两条有 sent_text
    sent_rows = [r for r in rows if r["sent_text"]]
    assert len(sent_rows) == 2
    assert "已发" in sent_rows[0]["sent_text"]


@pytest.mark.asyncio
async def test_export_empty_tenant(temp_db):
    """空 tenant 导出返回空列表（JSON）或只含 header（CSV）。"""
    exporter = DataExporter()
    data_json = await exporter.export_chats("empty_tenant", format="json")
    assert json.loads(data_json.decode("utf-8")) == []

    data_csv = await exporter.export_chats("empty_tenant", format="csv")
    lines = data_csv.decode("utf-8").strip().splitlines()
    assert len(lines) == 1  # 仅 header


@pytest.mark.asyncio
async def test_export_tenant_isolation(temp_db):
    """不同 tenant 数据严格隔离，不串行。"""
    await _seed_messages("tenant_0001", count=3)
    await _seed_messages("tenant_0002", count=1)
    exporter = DataExporter()

    data1 = json.loads((await exporter.export_chats("tenant_0001", format="json")).decode())
    data2 = json.loads((await exporter.export_chats("tenant_0002", format="json")).decode())

    assert len(data1) == 3
    assert len(data2) == 1
    ids1 = {r["msg_id"] for r in data1}
    ids2 = {r["msg_id"] for r in data2}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_export_summary_fields(temp_db):
    """export_summary 返回正确字段。"""
    await _seed_messages("tenant_0001", count=5)
    exporter = DataExporter()
    summary = await exporter.export_summary("tenant_0001")

    assert summary["tenant_id"] == "tenant_0001"
    assert summary["message_count"] == 5
    assert "customer_count" in summary
    assert "days_running" in summary
    assert summary["data_retention_days"] == 30
    assert "exported_at" in summary


@pytest.mark.asyncio
async def test_export_summary_empty(temp_db):
    """空 tenant 的 summary 消息数为 0。"""
    exporter = DataExporter()
    summary = await exporter.export_summary("no_such_tenant")
    assert summary["message_count"] == 0
    assert summary["customer_count"] == 0
    assert summary["days_running"] == 0
