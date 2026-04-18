"""FastAPI 端到端 happy path · TestClient。"""

from __future__ import annotations

import time

import pytest


@pytest.mark.asyncio
async def test_health(app_client):
    r = await app_client.get("/v1/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert body["tenants_loaded"] >= 1


@pytest.mark.asyncio
async def test_inbound_unknown_tenant(app_client):
    r = await app_client.post(
        "/v1/inbound",
        json={
            "tenant_id": "tenant_unknown",
            "chat_id": "c",
            "sender_id": "s",
            "sender_name": "测试",
            "text": "在么",
            "timestamp": int(time.time()),
        },
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_inbound_happy_path(app_client):
    r = await app_client.post(
        "/v1/inbound",
        json={
            "tenant_id": "tenant_0001",
            "chat_id": "wxid_chat",
            "sender_id": "wxid_a",
            "sender_name": "客户A",
            "text": "在么 老板",
            "timestamp": int(time.time()),
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "tenant_0001"
    assert body["model_route"] == "doubao_15pro"  # v3: greeting 走拟人冠军
    assert body["text"]
    assert body["intent"]["intent"] == "greeting"
    assert body["intent"]["risk"] == "low"


@pytest.mark.asyncio
async def test_full_flow_inbound_decide_sent(app_client):
    """4 步闭环：inbound → suggestion → decide(accept) → sent。"""
    # 1. inbound
    r1 = await app_client.post(
        "/v1/inbound",
        json={
            "tenant_id": "tenant_0001",
            "chat_id": "wxid_chat_b",
            "sender_id": "wxid_b",
            "sender_name": "客户B",
            "text": "这个多少钱",
            "timestamp": int(time.time()),
        },
    )
    assert r1.status_code == 200
    sug = r1.json()
    msg_id = sug["msg_id"]

    # 2. decide accept
    r2 = await app_client.post(
        f"/v1/outbound/{msg_id}/decide",
        json={
            "msg_id": msg_id,
            "decision": "accept",
            "reviewed_at": int(time.time()),
        },
    )
    assert r2.status_code == 200
    assert r2.json()["decision"] == "accept"

    # 3. sent ack
    r3 = await app_client.post(
        f"/v1/outbound/{msg_id}/sent",
        json={
            "msg_id": msg_id,
            "sent_at": int(time.time()),
            "success": True,
        },
    )
    assert r3.status_code == 200
    assert r3.json()["success"] is True


@pytest.mark.asyncio
async def test_decide_not_found(app_client):
    r = await app_client.post(
        "/v1/outbound/sug_doesnotexist/decide",
        json={
            "msg_id": "sug_doesnotexist",
            "decision": "accept",
            "reviewed_at": int(time.time()),
        },
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_pending_returns_recent(app_client):
    # 先扔一条
    await app_client.post(
        "/v1/inbound",
        json={
            "tenant_id": "tenant_0001",
            "chat_id": "wxid_pending_chat",
            "sender_id": "wxid_p",
            "sender_name": "客户P",
            "text": "在么哥",
            "timestamp": int(time.time()),
        },
    )

    r = await app_client.get("/v1/outbound/pending/tenant_0001?limit=5")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 1
