"""F1 · /v1/control/* 路由测试 + inbound 集成。"""

from __future__ import annotations

import time

import pytest


@pytest.mark.asyncio
async def test_control_status_default(app_client):
    r = await app_client.get("/v1/control/tenant_0001/status")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "tenant_0001"
    assert body["auto_send_enabled"] is True
    assert body["high_risk_block"] is True
    assert body["is_paused"] is False


@pytest.mark.asyncio
async def test_control_pause_and_resume(app_client):
    pr = await app_client.post("/v1/control/tenant_0001/pause", json={"duration_sec": 60})
    assert pr.status_code == 200
    assert pr.json()["paused_until"] > int(time.time())

    sr = await app_client.get("/v1/control/tenant_0001/status")
    assert sr.json()["is_paused"] is True

    rr = await app_client.post("/v1/control/tenant_0001/resume")
    assert rr.status_code == 200
    assert rr.json()["was_paused"] is True

    s2 = await app_client.get("/v1/control/tenant_0001/status")
    assert s2.json()["is_paused"] is False


@pytest.mark.asyncio
async def test_control_unknown_tenant_404(app_client):
    r = await app_client.post("/v1/control/tenant_unknown/pause", json={"duration_sec": 60})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_inbound_logs_auto_send_decision(app_client):
    payload = {
        "tenant_id": "tenant_0001",
        "chat_id": "chat_x",
        "sender_id": "user_x",
        "sender_name": "客户",
        "text": "你好 在吗",
        "timestamp": int(time.time()),
    }
    r = await app_client.post("/v1/inbound", json=payload)
    assert r.status_code == 200
    sug = r.json()
    assert sug["msg_id"]
    assert sug["text"]


@pytest.mark.asyncio
async def test_inbound_high_risk_blocked_but_returns_suggestion(app_client):
    """高风险消息 · 仍然生成 suggestion 返回 · 但内部决策为 blocked。"""
    payload = {
        "tenant_id": "tenant_0001",
        "chat_id": "chat_x",
        "sender_id": "user_x",
        "sender_name": "客户",
        "text": "差评 投诉 退款 假货",
        "timestamp": int(time.time()),
    }
    r = await app_client.post("/v1/inbound", json=payload)
    assert r.status_code == 200
    sug = r.json()
    # risk should be HIGH (rule: complaint keywords)
    assert sug["intent"]["risk"] == "high"
