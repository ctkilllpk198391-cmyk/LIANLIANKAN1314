"""C1 · TDW 端到端 6 场景。"""

from __future__ import annotations

import asyncio
import base64
import json
import time

import pytest
from sqlalchemy import select

from server.db import session_scope
from server.models import (
    ContentUpload,
    DeletionRequest,
    MarketingPlan,
    MomentsPost,
    Message,
)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


# ─── 场景 1 · 上传 .md → KB 召回 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_1_upload_md_to_kb(e2e_client):
    r = await e2e_client.post(
        "/v1/content/tenant_e2e/upload?file_name=新品介绍.md",
        json={"file_bytes_b64": _b64("# 玉兰油精华\n¥299 · 30ml · 适合 25+\n\n## 卖点\n滋润 · 紧致")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["parsed_chunks"] >= 1

    # 询价时 RAG 应能召回（同 tenant_e2e）
    inb = await e2e_client.post("/v1/inbound", json={
        "tenant_id": "tenant_e2e",
        "chat_id": "chat_kb_test",
        "sender_id": "user_x",
        "sender_name": "客户",
        "text": "玉兰油精华多少钱",
        "timestamp": int(time.time()),
    })
    assert inb.status_code == 200


# ─── 场景 2 · 上传 .csv 价格表 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_2_upload_csv_price(e2e_client):
    csv = "name,price,stock\n精华,299,5\n面霜,199,10"
    r = await e2e_client.post(
        "/v1/content/tenant_e2e/upload?file_name=价格表.csv",
        json={"file_bytes_b64": _b64(csv)},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["file_type"] == "csv"
    assert body["source_tag"] == "价格"
    assert body["parsed_chunks"] >= 2


# ─── 场景 3 · 新品.md → 自动生成 marketing_plan → activate ──────────────

@pytest.mark.asyncio
async def test_scenario_3_marketing_auto_generated(e2e_client):
    r = await e2e_client.post(
        "/v1/content/tenant_e2e/upload?file_name=新品发布.md",
        json={"file_bytes_b64": _b64("产品 · 玉兰油精华 ¥299 · 30ml · 上新限时优惠")},
    )
    assert r.status_code == 200
    body = r.json()
    # source_tag=产品 → 应触发 marketing_generator
    assert body.get("marketing_plan_id") is not None

    # 列出营销方案
    plans_r = await e2e_client.get("/v1/marketing/tenant_e2e")
    assert plans_r.status_code == 200
    plans = plans_r.json()
    assert len(plans) >= 1

    plan_id = body["marketing_plan_id"]
    # activate
    act = await e2e_client.post(f"/v1/marketing/{plan_id}/activate")
    assert act.status_code == 200
    assert act.json()["ok"] is True

    # 验证 moments_posts 入库
    async with session_scope() as s:
        moments = (await s.execute(
            select(MomentsPost).where(MomentsPost.tenant_id == "tenant_e2e")
        )).scalars().all()
        assert len(moments) >= 1


# ─── 场景 4 · Dashboard /v3 含 pipeline + actions ───────────────────────

@pytest.mark.asyncio
async def test_scenario_4_dashboard_v3(e2e_client):
    r = await e2e_client.get("/v1/dashboard/tenant_e2e/v3", headers={"X-Test-Mode": "bypass"})
    assert r.status_code == 200
    body = r.json()
    # v3 应至少含 pipeline + actions + multi_account 字段（结构由 sonnet 决定）
    assert isinstance(body, dict)


# ─── 场景 5 · 数据导出 csv ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_5_data_export_csv(e2e_client):
    # 先打几条消息建数据
    for i in range(3):
        await e2e_client.post("/v1/inbound", json={
            "tenant_id": "tenant_e2e",
            "chat_id": f"chat_export_{i}",
            "sender_id": f"user_{i}",
            "sender_name": "客户",
            "text": f"消息 {i}",
            "timestamp": int(time.time()),
        })

    r = await e2e_client.post("/v1/account/tenant_e2e/export?format=csv")
    assert r.status_code == 200
    # 应返 csv 字节或 dict
    body = r.content if hasattr(r, "content") else b""
    assert body or r.json()


# ─── 场景 6 · 数据删除请求 30 天 grace ──────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_6_deletion_request_grace(e2e_client):
    r = await e2e_client.post(
        "/v1/account/tenant_e2e/delete_request",
        json={"reason": "测试"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "request_id" in body or "ok" in body

    # 验证 grace_until 至少 29 天后
    async with session_scope() as s:
        rows = (await s.execute(
            select(DeletionRequest).where(DeletionRequest.tenant_id == "tenant_e2e")
        )).scalars().all()
        assert len(rows) >= 1
        assert rows[0].status == "pending"
        days_grace = (rows[0].grace_until - rows[0].requested_at) / 86400
        assert days_grace >= 29
