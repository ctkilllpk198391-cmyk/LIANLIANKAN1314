"""T2 · 营销方案生成 + activate 测试。"""

from __future__ import annotations

import json
import time

import pytest
from sqlalchemy import select

from server.db import session_scope
from server.marketing_plan import (
    GroupBroadcast,
    MarketingPlanActivator,
    MarketingPlanData,
    MarketingPlanGenerator,
    MomentPostDraft,
    PrivateChatSOP,
    list_plans,
)
from server.models import FollowUpTask, MarketingPlan, MomentsPost


@pytest.mark.asyncio
async def test_generate_with_no_llm_fallback(temp_db):
    gen = MarketingPlanGenerator(llm_client=None)
    plan_id = await gen.generate(
        tenant_id="tenant_0001",
        source_content_id="content_xxx",
        source_text="玉兰油精华上新 ¥299",
    )
    assert plan_id.startswith("mp_")

    async with session_scope() as s:
        row = (await s.execute(
            select(MarketingPlan).where(MarketingPlan.plan_id == plan_id)
        )).scalar_one()
        assert row.status == "draft"
        payload = json.loads(row.payload_json)
        assert len(payload["moments_posts"]) >= 1
        assert len(payload["private_sops"]) >= 1
        assert len(payload["group_broadcasts"]) >= 1


@pytest.mark.asyncio
async def test_generate_with_llm_mock_returns_json(temp_db):
    class MockLLM:
        async def respond(self, **kwargs):
            return json.dumps({
                "moments_posts": [
                    {"day_offset": 0, "angle": "开抢", "content": "上新啦", "suggested_image": "玉兰油"}
                ],
                "private_sops": [
                    {"trigger": "客户问活动", "reply_template": "亲今天最后一天"}
                ],
                "group_broadcasts": [
                    {"target_tier": "A", "text": "VIP 专属"}
                ],
                "estimated_impact": {"expected_orders": 5, "expected_revenue": 1495},
            })

    gen = MarketingPlanGenerator(llm_client=MockLLM())
    plan_id = await gen.generate(
        tenant_id="tenant_0001",
        source_text="新品资料",
    )
    plans = await list_plans("tenant_0001")
    assert len(plans) == 1
    assert plans[0]["payload"]["estimated_impact"]["expected_orders"] == 5


@pytest.mark.asyncio
async def test_generate_llm_invalid_json_falls_back(temp_db):
    class BadLLM:
        async def respond(self, **kwargs):
            return "我觉得应该这样做但我不会写 JSON"

    gen = MarketingPlanGenerator(llm_client=BadLLM())
    plan_id = await gen.generate(tenant_id="tenant_0001", source_text="x")
    plans = await list_plans("tenant_0001")
    assert len(plans) == 1   # fallback 仍生成


@pytest.mark.asyncio
async def test_activate_creates_moments_and_broadcasts(temp_db):
    gen = MarketingPlanGenerator(llm_client=None)
    plan_id = await gen.generate(
        tenant_id="tenant_0001",
        source_text="双11 预热活动",
    )

    activator = MarketingPlanActivator()
    result = await activator.activate(plan_id)
    assert result["ok"] is True
    assert result["moments_scheduled"] >= 1
    assert result["broadcasts_scheduled"] >= 1

    # 验证 moments_posts 入库
    async with session_scope() as s:
        moments = (await s.execute(
            select(MomentsPost).where(MomentsPost.tenant_id == "tenant_0001")
        )).scalars().all()
        assert len(moments) >= 1
        assert moments[0].status == "scheduled"

        bcs = (await s.execute(
            select(FollowUpTask).where(FollowUpTask.tenant_id == "tenant_0001")
            .where(FollowUpTask.task_type.like("broadcast_%"))
        )).scalars().all()
        assert len(bcs) >= 1


@pytest.mark.asyncio
async def test_activate_idempotent(temp_db):
    gen = MarketingPlanGenerator(llm_client=None)
    plan_id = await gen.generate(tenant_id="tenant_0001", source_text="x")

    activator = MarketingPlanActivator()
    r1 = await activator.activate(plan_id)
    r2 = await activator.activate(plan_id)
    assert r1["ok"] is True
    assert r2["ok"] is False
    assert "already active" in r2["reason"]


@pytest.mark.asyncio
async def test_activate_unknown_plan(temp_db):
    activator = MarketingPlanActivator()
    r = await activator.activate("mp_nonexistent")
    assert r["ok"] is False
    assert "not found" in r["reason"]


@pytest.mark.asyncio
async def test_list_plans_filter_by_status(temp_db):
    gen = MarketingPlanGenerator(llm_client=None)
    pid1 = await gen.generate(tenant_id="tenant_0001", source_text="a")
    pid2 = await gen.generate(tenant_id="tenant_0001", source_text="b")

    activator = MarketingPlanActivator()
    await activator.activate(pid1)

    drafts = await list_plans("tenant_0001", status="draft")
    actives = await list_plans("tenant_0001", status="active")
    assert len(drafts) == 1
    assert len(actives) == 1


@pytest.mark.asyncio
async def test_tenant_isolation(temp_db):
    gen = MarketingPlanGenerator(llm_client=None)
    await gen.generate(tenant_id="tenant_A", source_text="a")
    await gen.generate(tenant_id="tenant_B", source_text="b")
    plans_a = await list_plans("tenant_A")
    plans_b = await list_plans("tenant_B")
    assert len(plans_a) == 1
    assert len(plans_b) == 1
    assert plans_a[0]["plan_id"] != plans_b[0]["plan_id"]


def test_marketing_plan_data_dataclass():
    p = MarketingPlanData(plan_id="x", tenant_id="t", source_content_id=None)
    assert p.moments_posts == []
    assert p.status == "draft"
