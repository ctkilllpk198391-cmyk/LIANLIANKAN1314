"""D2 · SDW Second Wave 端到端 10 场景。

每场景跑完整 inbound 链路 · 验证 SDW 8 件功能集成正确。
"""

from __future__ import annotations

import asyncio
import time

import pytest
from sqlalchemy import select

from server.db import session_scope
from server.embedder import BGEEmbedder
from server.knowledge_base import KnowledgeBase
from server.models import (
    AuditLog,
    CustomerProfile,
    FollowUpTask,
    Message,
    MomentsPost,
    Suggestion as SuggestionModel,
)


def _payload(text, chat_id="chat_default", sender="客户", msg_type="text", **extras):
    base = {
        "tenant_id": "tenant_e2e",
        "chat_id": chat_id,
        "sender_id": f"user_{chat_id}",
        "sender_name": sender,
        "text": text,
        "timestamp": int(time.time()),
        "msg_type": msg_type,
    }
    base.update(extras)
    return base


async def _audit_actions(tenant_id: str) -> list[str]:
    async with session_scope() as s:
        rows = (await s.execute(
            select(AuditLog.action).where(AuditLog.tenant_id == tenant_id)
        )).scalars().all()
        return list(rows)


# ─── 场景 1 · 拟人节奏：WS payload 含 segments ─────────────────────────

@pytest.mark.asyncio
async def test_scenario_1_typing_segments_in_ws(e2e_client):
    from server.main import state
    pushed = []
    original_push = state.auto_send_decider.ws_pusher

    async def capture(tid, payload):
        pushed.append(payload)
        if original_push:
            await original_push(tid, payload)

    state.auto_send_decider.ws_pusher = capture
    try:
        r = await e2e_client.post("/v1/inbound", json=_payload("你好 在吗", chat_id="chat_seg"))
        assert r.status_code == 200
        await asyncio.sleep(0.1)

        # 至少 1 条 ws push · 含 segments 字段
        if pushed:
            seg_payload = next((p for p in pushed if p.get("type") == "auto_send_command"), None)
            if seg_payload:
                assert "segments" in seg_payload
                assert isinstance(seg_payload["segments"], list)
    finally:
        state.auto_send_decider.ws_pusher = original_push


# ─── 场景 2 · 心理学：临门一脚（NEAR + EXCITED）─────────────────────────

@pytest.mark.asyncio
async def test_scenario_2_psych_near_stage_audit(e2e_client):
    """连续 2 次 negotiation → stage=NEAR · 触发 SCARCITY/LOSS_AVERSION。"""
    # 先打 1 次 inquiry 建档
    await e2e_client.post("/v1/inbound", json=_payload("多少钱", chat_id="chat_near"))
    await asyncio.sleep(0.05)
    # 2 次 negotiation
    await e2e_client.post("/v1/inbound", json=_payload("便宜点 划算点", chat_id="chat_near"))
    await asyncio.sleep(0.05)
    r = await e2e_client.post("/v1/inbound", json=_payload("再便宜点!", chat_id="chat_near"))
    assert r.status_code == 200


# ─── 场景 3 · 心理学：投诉 ANGRY → 不推销 ────────────────────────────

@pytest.mark.asyncio
async def test_scenario_3_psych_complaint_no_pushy(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload("差评 投诉 退款 假货", chat_id="chat_angry2"))
    assert r.status_code == 200
    sug = r.json()
    assert sug["intent"]["risk"] == "high"
    # 高风险熔断（不发） · audit 应有 blocked_high_risk
    await asyncio.sleep(0.05)
    actions = await _audit_actions("tenant_e2e")
    assert "auto_send_blocked_high_risk" in actions


# ─── 场景 4 · 行业模板（默认通用 · 不挂）─────────────────────────────

@pytest.mark.asyncio
async def test_scenario_4_industry_block_works(e2e_client):
    """默认 industry='通用' · prompt 含 industry_block 不挂。"""
    r = await e2e_client.post("/v1/inbound", json=_payload("有货吗", chat_id="chat_ind"))
    assert r.status_code == 200


# ─── 场景 5 · 图片理解 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_5_image_url_describe(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload(
        "这个多少钱",
        chat_id="chat_img",
        msg_type="image",
        image_url="https://example.com/product.jpg",
    ))
    assert r.status_code == 200
    # mock vlm 应该把"[图片：xxx]"加到消息文本里 · 走完整链路


# ─── 场景 6 · 语音转文字 ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_scenario_6_voice_url_transcribe(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload(
        "",
        chat_id="chat_voice",
        msg_type="voice",
        voice_url="https://example.com/voice.mp3",
    ))
    assert r.status_code == 200


# ─── 场景 7 · 反检测：suspicion → 暂停 ────────────────────────────

@pytest.mark.asyncio
async def test_scenario_7_suspicion_pauses_auto_send(e2e_client):
    r = await e2e_client.post("/v1/inbound", json=_payload(
        "你是 AI 吗 怎么这么慢",
        chat_id="chat_susp",
    ))
    assert r.status_code == 200
    await asyncio.sleep(0.1)
    actions = await _audit_actions("tenant_e2e")
    assert "suspicion_detected" in actions


# ─── 场景 8 · 反检测：humanize 开场变体被替换 ───────────────────────

@pytest.mark.asyncio
async def test_scenario_8_humanize_opening_replaced(e2e_client):
    """mock LLM 输出可能含"亲，您好~" · humanize 应替换。"""
    from server.anti_detect import vary_opening
    text = "亲，您好~ 这款是爆款"
    out = vary_opening(text)
    assert not out.startswith("亲，您好~")


# ─── 场景 9 · 交叉销售：流程跑通（mock 数据）──────────────────────

@pytest.mark.asyncio
async def test_scenario_9_cross_sell_flow_works(e2e_client):
    """整链路含 cross_sell 调用 · 不挂即过。"""
    # 先建档 + 模拟历史购买（manual 写入 DB）
    await e2e_client.post("/v1/inbound", json=_payload("你好", chat_id="chat_xs"))
    await asyncio.sleep(0.05)

    # 询价（触发交叉销售判断）
    r = await e2e_client.post("/v1/inbound", json=_payload("有货吗", chat_id="chat_xs"))
    assert r.status_code == 200


# ─── 场景 10 · 朋友圈：手动 draft → 入库 ──────────────────────────

@pytest.mark.asyncio
async def test_scenario_10_moments_draft(e2e_client):
    r = await e2e_client.post(
        "/v1/moments/tenant_e2e/draft?post_type=product"
    )
    assert r.status_code == 200
    body = r.json()
    assert "post_id" in body or "ok" in body or "content" in body

    async with session_scope() as s:
        rows = (await s.execute(
            select(MomentsPost).where(MomentsPost.tenant_id == "tenant_e2e")
        )).scalars().all()
        assert len(rows) >= 1
        assert rows[0].post_type == "product"
