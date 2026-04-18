"""审计链验证 · 一条消息全链 4 节点都在 audit_log。"""

from __future__ import annotations

import time

import pytest
from sqlalchemy import select

from server.db import session_scope
from server.models import AuditLog


@pytest.mark.asyncio
async def test_audit_chain_full_flow(app_client):
    payload_in = {
        "tenant_id": "tenant_0001",
        "chat_id": "wxid_audit",
        "sender_id": "wxid_aud",
        "sender_name": "审计测试",
        "text": "在么 准备买点东西",
        "timestamp": int(time.time()),
    }
    r1 = await app_client.post("/v1/inbound", json=payload_in)
    assert r1.status_code == 200
    sug = r1.json()
    msg_id = sug["msg_id"]

    await app_client.post(
        f"/v1/outbound/{msg_id}/decide",
        json={"msg_id": msg_id, "decision": "accept", "reviewed_at": int(time.time())},
    )

    await app_client.post(
        f"/v1/outbound/{msg_id}/sent",
        json={"msg_id": msg_id, "sent_at": int(time.time()), "success": True},
    )

    async with session_scope() as session:
        rows = (
            await session.execute(
                select(AuditLog).where(AuditLog.tenant_id == "tenant_0001").order_by(AuditLog.id)
            )
        ).scalars().all()
        actions = [r.action for r in rows]

    # 至少包含 4 个核心节点
    expected_actions = {"inbound_received", "suggestion_generated", "reviewed", "sent"}
    assert expected_actions.issubset(set(actions)), f"missing: {expected_actions - set(actions)}"
