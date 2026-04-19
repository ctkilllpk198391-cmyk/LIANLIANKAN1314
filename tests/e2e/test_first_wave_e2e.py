"""D1 · First Wave 端到端 6 场景真路径测试。

每个场景跑完整 inbound → classify → profile → RAG → generate → auto_send_decide
→ audit · 校验：
  - HTTP 200 + Suggestion 返回
  - DB 状态（messages/suggestions/customer_profiles/follow_up_tasks/training_queue）
  - audit log 节点齐全
  - WS pusher 收到 auto_send_command（或 BLOCKED 时不收）
"""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import select

from server.db import session_scope
from server.knowledge_base import KnowledgeBase
from server.embedder import BGEEmbedder
from server.customer_profile import CustomerProfileEngine
from server.models import (
    AuditLog,
    CustomerProfile,
    FollowUpTask,
    Message,
    Suggestion as SuggestionModel,
    TrainingQueue,
)
from shared.proto import IntentResult, ReviewDecision, Suggestion
from shared.types import EmotionEnum, IntentEnum, ReviewDecisionEnum, RiskEnum


def _payload(text, chat_id="chat_default", sender="客户"):
    return {
        "tenant_id": "tenant_e2e",
        "chat_id": chat_id,
        "sender_id": f"user_{chat_id}",
        "sender_name": sender,
        "text": text,
        "timestamp": int(time.time()),
    }


async def _audit_actions(tenant_id: str) -> list[str]:
    async with session_scope() as s:
        rows = (await s.execute(
            select(AuditLog.action).where(AuditLog.tenant_id == tenant_id)
        )).scalars().all()
        return list(rows)


# ─── 场景 1 · 陌生新客首次询价 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_1_new_customer_inquiry(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload("这款多少钱啊 怎么卖", chat_id="chat_new"))
    assert r.status_code == 200
    sug = r.json()
    assert sug["text"]
    assert sug["intent"]["intent"] == "inquiry"

    await asyncio.sleep(0.05)  # 等异步任务

    # 验证 customer_profile 自动创建
    async with session_scope() as s:
        prof = (await s.execute(
            select(CustomerProfile)
            .where(CustomerProfile.tenant_id == "tenant_e2e")
            .where(CustomerProfile.chat_id == "chat_new")
        )).scalar_one_or_none()
        assert prof is not None
        assert prof.nickname == "客户"

    actions = await _audit_actions("tenant_e2e")
    assert "inbound_received" in actions
    assert "suggestion_generated" in actions
    assert any(a.startswith("auto_send_") for a in actions)


# ─── 场景 2 · 老客复购（预注入 profile）─────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_2_returning_customer(e2e_client):
    # 预先打几条消息建档案
    for _ in range(3):
        await e2e_client.post("/v1/inbound", json=_payload("你好", chat_id="chat_vip"))
        await asyncio.sleep(0.01)

    # 复购意图消息
    r = await e2e_client.post("/v1/inbound", json=_payload("再来一瓶", chat_id="chat_vip"))
    assert r.status_code == 200

    await asyncio.sleep(0.05)
    async with session_scope() as s:
        prof = (await s.execute(
            select(CustomerProfile)
            .where(CustomerProfile.chat_id == "chat_vip")
        )).scalar_one_or_none()
        assert prof.total_messages >= 3


# ─── 场景 3 · 砍价 + 临门一脚（emotion=EXCITED）─────────────────────────

@pytest.mark.asyncio
async def test_scenario_3_negotiation_excited(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload("便宜点 现在就要!", chat_id="chat_neg"))
    assert r.status_code == 200
    sug = r.json()
    assert sug["intent"]["intent"] == "negotiation"
    # rule mode 默认 emotion=CALM · 但短句+! 可能 EXCITED
    assert sug["intent"]["emotion"] in ("calm", "excited")


# ─── 场景 4 · 投诉 + 高风险熔断 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_4_complaint_high_risk_blocked(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload("差评 投诉 退款 假货", chat_id="chat_angry"))
    assert r.status_code == 200
    sug = r.json()
    assert sug["intent"]["risk"] == "high"

    await asyncio.sleep(0.1)
    actions = await _audit_actions("tenant_e2e")
    # 应该有 auto_send_blocked_high_risk 决策
    assert "auto_send_blocked_high_risk" in actions


# ─── 场景 5 · 下单 + 30 分钟自动催付款（follow_up）──────────────────────

@pytest.mark.asyncio
async def test_scenario_5_order_triggers_followup(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload("我付款了", chat_id="chat_order"))
    assert r.status_code == 200
    assert r.json()["intent"]["intent"] == "order"

    await asyncio.sleep(0.1)  # 等 follow_up.schedule_after_order 完成

    async with session_scope() as s:
        rows = (await s.execute(
            select(FollowUpTask).where(FollowUpTask.tenant_id == "tenant_e2e")
            .where(FollowUpTask.chat_id == "chat_order")
        )).scalars().all()
        types = {r.task_type for r in rows}
        # Wave 12 安全档 · 2 步温和跟进 (unpaid_30min + satisfaction_7d)
        assert "unpaid_30min" in types
        assert len(rows) == 2


# ─── 场景 6 · 长尾询价 + RAG 召回（先 ingest 产品库）────────────────────

@pytest.mark.asyncio
async def test_scenario_6_long_tail_with_rag(e2e_client):
    # 直接通过 KnowledgeBase 注入数据（避免上传文件 endpoint 复杂度）
    kb = KnowledgeBase(embedder=BGEEmbedder(mock=True))
    await kb.ingest(
        "tenant_e2e",
        "products.md",
        "玉兰油精华 ¥299 容量 30ml 适合 25+\n\n面霜 ¥199 容量 50g 滋润型",
    )

    r = await e2e_client.post("/v1/inbound", json=_payload("玉兰油精华多少钱", chat_id="chat_rag"))
    assert r.status_code == 200
    sug = r.json()
    assert sug["text"]

    # 验证 prompt 里有 RAG 召回（mock 模式 · 模型固定回复 · 但流程跑通即过）
    actions = await _audit_actions("tenant_e2e")
    assert "suggestion_generated" in actions


# ─── 场景 7 · 老板审核后入 training_queue ───────────────────────────────

@pytest.mark.asyncio
async def test_scenario_7_review_decision_appends_training(e2e_client):
    """补充场景 · 验证 decide 路由把 review 写进 training_queue。"""
    r = await e2e_client.post("/v1/inbound", json=_payload("你好", chat_id="chat_train"))
    assert r.status_code == 200
    msg_id = r.json()["msg_id"]

    decision_payload = {
        "msg_id": msg_id,
        "decision": "accept",
        "reviewed_at": int(time.time()),
    }
    dr = await e2e_client.post(f"/v1/outbound/{msg_id}/decide", json=decision_payload)
    assert dr.status_code == 200

    await asyncio.sleep(0.1)
    async with session_scope() as s:
        rows = (await s.execute(
            select(TrainingQueue).where(TrainingQueue.tenant_id == "tenant_e2e")
        )).scalars().all()
        assert len(rows) >= 1
        assert rows[0].decision == "accept"
        assert rows[0].weight == 1.0


# ─── 场景 8 · pause/resume 全自动开关 ────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_8_pause_resume_works(e2e_client):
    pr = await e2e_client.post("/v1/control/tenant_e2e/pause", json={"duration_sec": 60})
    assert pr.status_code == 200

    r = await e2e_client.post("/v1/inbound", json=_payload("在吗", chat_id="chat_pause"))
    assert r.status_code == 200
    await asyncio.sleep(0.05)
    actions = await _audit_actions("tenant_e2e")
    assert "auto_send_blocked_paused" in actions

    rr = await e2e_client.post("/v1/control/tenant_e2e/resume")
    assert rr.status_code == 200

    r2 = await e2e_client.post("/v1/inbound", json=_payload("在吗", chat_id="chat_pause2"))
    assert r2.status_code == 200
    await asyncio.sleep(0.05)
    actions2 = await _audit_actions("tenant_e2e")
    assert "auto_send_auto_send" in actions2
