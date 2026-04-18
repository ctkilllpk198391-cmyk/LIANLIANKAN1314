"""B2 · FDW+ 端到端 5 场景。"""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import select

from server.db import session_scope
from server.models import ActivationCode, AuditLog, DeviceBinding


# ─── 场景 1 · 激活码：发码 → 激活 → token 工作 ─────────────────────────

@pytest.mark.asyncio
async def test_scenario_1_activation_flow(e2e_client):
    from server.activation import ActivationService
    svc = ActivationService()

    # 生成激活码（绕过 admin auth · 直接调 service）
    code = await svc.generate_code_async(plan="pro", valid_days=365)
    assert code.startswith("WXA-2026-")

    # 激活
    activate_r = await e2e_client.post(
        "/v1/activate",
        json={"code": code, "machine_guid": "test_machine_001", "tenant_id": "tenant_e2e"},
    )
    assert activate_r.status_code == 200
    body = activate_r.json()
    assert "device_token" in body
    token = body["device_token"]

    # 用 token 访问 dashboard /v3
    dash_r = await e2e_client.get(
        "/v1/dashboard/tenant_e2e/v3",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert dash_r.status_code == 200


# ─── 场景 2 · Web 登录 鉴权失败 → 401 ──────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_2_no_token_returns_401(e2e_client):
    r = await e2e_client.get("/v1/dashboard/tenant_e2e/v3")
    assert r.status_code == 401


# ─── 场景 3 · 自动更新 · /v1/version 返回最新 ──────────────────────────

@pytest.mark.asyncio
async def test_scenario_3_version_api(e2e_client):
    r = await e2e_client.get("/v1/version")
    assert r.status_code == 200
    body = r.json()
    assert "latest_version" in body
    assert "download_url" in body
    assert "min_supported" in body


# ─── 场景 4 · 灰产拒绝 → AI 不生成 + audit ────────────────────────────

@pytest.mark.asyncio
async def test_scenario_4_compliance_blocks_gambling(e2e_client):
    r = await e2e_client.post("/v1/inbound", json={
        "tenant_id": "tenant_e2e",
        "chat_id": "chat_gamble",
        "sender_id": "user_x",
        "sender_name": "客户",
        "text": "我们一起玩百家乐 下注",
        "timestamp": int(time.time()),
    })
    assert r.status_code == 200
    sug = r.json()
    assert sug["model_route"] == "compliance_block"
    assert "服务范围" in sug["text"] or "抱歉" in sug["text"]

    await asyncio.sleep(0.05)
    async with session_scope() as s:
        rows = (await s.execute(
            select(AuditLog.action).where(AuditLog.tenant_id == "tenant_e2e")
            .where(AuditLog.action == "compliance_blocked")
        )).scalars().all()
        assert len(rows) >= 1


# ─── 场景 5 · 紧急停止（举报检测）────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_5_emergency_stop(e2e_client):
    r = await e2e_client.post(
        "/v1/control/tenant_e2e/emergency_stop",
        json={"alert_text": "您的账号被举报", "pattern": "被举报", "detected_at": int(time.time())},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["paused_until"] > int(time.time())

    # 验证 audit
    async with session_scope() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.tenant_id == "tenant_e2e")
            .where(AuditLog.action == "emergency_stop_wechat_alert")
        )).scalars().all()
        assert len(rows) >= 1


# ─── 场景 6 · 律师举证导出 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_6_legal_export(e2e_client):
    # 先建几条 audit
    await e2e_client.post("/v1/inbound", json={
        "tenant_id": "tenant_e2e",
        "chat_id": "chat_legal",
        "sender_id": "u",
        "sender_name": "客户",
        "text": "你好",
        "timestamp": int(time.time()),
    })
    await asyncio.sleep(0.05)

    r = await e2e_client.get("/v1/admin/legal_export/tenant_e2e")
    assert r.status_code == 200
    body = r.json()
    assert body["tenant_id"] == "tenant_e2e"
    assert "audit_log_csv_preview" in body
    assert "tenant_summary_md" in body
    assert "v3 协议" in body["tenant_summary_md"]
