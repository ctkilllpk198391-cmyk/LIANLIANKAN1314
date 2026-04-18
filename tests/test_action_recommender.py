"""T3 · ActionRecommender 测试 · ≥6 用例。"""

from __future__ import annotations

import json
import time

import pytest

from server.action_recommender import ActionRecommender, _last_purchase_days, _in_repurchase_window


# ─── helpers ─────────────────────────────────────────────────────────────────

def _make_profile(
    chat_id: str = "chat_test",
    tenant_id: str = "tenant_0001",
    nickname: str = "测试用户",
    vip_tier: str = "B",
    last_intent: str | None = None,
    last_message_at: int | None = None,
    purchase_history: list | None = None,
    last_emotion: str = "calm",
):
    """创建一个假 CustomerProfile 对象（不需要 DB）。"""
    from types import SimpleNamespace
    now = int(time.time())
    return SimpleNamespace(
        chat_id=chat_id,
        tenant_id=tenant_id,
        nickname=nickname,
        vip_tier=vip_tier,
        last_intent=last_intent,
        last_message_at=last_message_at if last_message_at is not None else now,
        last_emotion=last_emotion,
        purchase_history=json.dumps(purchase_history) if purchase_history is not None else "[]",
    )


async def _insert_profile(session, tenant_id, chat_id, **kwargs):
    from server.models import CustomerProfile as CPModel
    now = int(time.time())
    defaults = dict(
        vip_tier="B",
        last_intent=None,
        last_message_at=now,
        last_emotion="calm",
        total_messages=3,
        accepted_replies=1,
        updated_at=now,
        purchase_history="[]",
    )
    defaults.update(kwargs)
    session.add(CPModel(tenant_id=tenant_id, chat_id=chat_id, **defaults))
    await session.flush()


# ─── 1. 辅助函数测试 ──────────────────────────────────────────────────────────

def test_last_purchase_days_empty():
    assert _last_purchase_days("[]") is None


def test_last_purchase_days_no_json():
    assert _last_purchase_days(None) is None


def test_last_purchase_days_with_history():
    now = int(time.time())
    history = [{"date": now - 30 * 86400, "amount": 100, "sku": "A"}]
    days = _last_purchase_days(json.dumps(history))
    assert days is not None
    assert 29 <= days <= 31


def test_in_repurchase_window_exact():
    assert _in_repurchase_window(30, 30) is True


def test_in_repurchase_window_tolerance():
    assert _in_repurchase_window(32, 30) is True   # +2 在容差内
    assert _in_repurchase_window(27, 30) is True   # -3 在容差内


def test_in_repurchase_window_out():
    assert _in_repurchase_window(40, 30) is False


# ─── 2. recommend_for_customer 规则 1：complaint → handoff ────────────────────

@pytest.mark.asyncio
async def test_recommend_complaint_handoff():
    recommender = ActionRecommender()
    profile = _make_profile(last_intent="complaint")
    action = await recommender.recommend_for_customer(profile)

    assert action is not None
    assert action.action_type == "handoff"
    assert action.confidence >= 0.9


# ─── 3. 规则 2：30+ 天 → care ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_stale_care():
    recommender = ActionRecommender()
    now = int(time.time())
    profile = _make_profile(
        last_message_at=now - 35 * 86400,
        last_intent="greeting",
    )
    action = await recommender.recommend_for_customer(profile)

    assert action is not None
    assert action.action_type == "care"
    assert "关怀" in action.reason


# ─── 4. 规则 3：inquiry + 1d → follow_up ─────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_inquiry_followup():
    recommender = ActionRecommender()
    now = int(time.time())
    profile = _make_profile(
        last_intent="inquiry",
        last_message_at=now - 2 * 86400,
    )
    action = await recommender.recommend_for_customer(profile)

    assert action is not None
    assert action.action_type == "follow_up"


# ─── 5. 规则 4：复购窗口 → repurchase ────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_repurchase_window():
    recommender = ActionRecommender()
    now = int(time.time())
    history = [{"date": now - 30 * 86400, "amount": 500, "sku": "B"}]
    profile = _make_profile(
        vip_tier="B",
        last_intent="greeting",
        last_message_at=now - 5 * 86400,
        purchase_history=history,
    )
    action = await recommender.recommend_for_customer(profile)

    assert action is not None
    assert action.action_type == "repurchase"


# ─── 6. 规则 5：A 客户 7d → upsell ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_vip_a_upsell():
    recommender = ActionRecommender()
    now = int(time.time())
    profile = _make_profile(
        vip_tier="A",
        last_intent="greeting",
        last_message_at=now - 10 * 86400,
    )
    action = await recommender.recommend_for_customer(profile)

    assert action is not None
    assert action.action_type == "upsell"


# ─── 7. 无行动触发 → None ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_no_action():
    recommender = ActionRecommender()
    now = int(time.time())
    profile = _make_profile(
        vip_tier="C",
        last_intent="greeting",
        last_message_at=now,  # 刚刚联系过
    )
    action = await recommender.recommend_for_customer(profile)
    assert action is None


# ─── 8. recommend_top_n 空库返回空列表 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_top_n_empty_db(temp_db, loaded_tenants):
    recommender = ActionRecommender()
    result = await recommender.recommend_top_n("tenant_0001", n=10)
    assert result == []


# ─── 9. recommend_top_n 有客户时按 confidence 排序 ───────────────────────────

@pytest.mark.asyncio
async def test_recommend_top_n_sorted_by_confidence(temp_db, loaded_tenants):
    from server.db import session_scope

    now = int(time.time())

    async with session_scope() as session:
        # complaint → handoff (0.95)
        await _insert_profile(
            session, "tenant_0001", "chat_complaint",
            last_intent="complaint",
            last_message_at=now - 86400,
        )
        # care (0.85)
        await _insert_profile(
            session, "tenant_0001", "chat_stale",
            last_intent="greeting",
            last_message_at=now - 40 * 86400,
        )

    recommender = ActionRecommender()
    result = await recommender.recommend_top_n("tenant_0001", n=10)

    assert len(result) >= 2
    confidences = [a.confidence for a in result]
    assert confidences == sorted(confidences, reverse=True)
    assert result[0].action_type == "handoff"


# ─── 10. recommend_top_n n 限制 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_top_n_limit(temp_db, loaded_tenants):
    from server.db import session_scope

    now = int(time.time())

    async with session_scope() as session:
        for i in range(5):
            await _insert_profile(
                session, "tenant_0001", f"chat_complaint_{i}",
                last_intent="complaint",
                last_message_at=now - 86400,
            )

    recommender = ActionRecommender()
    result = await recommender.recommend_top_n("tenant_0001", n=3)
    assert len(result) <= 3


# ─── 11. suggested_text 不为空 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_recommend_suggested_text_not_empty():
    recommender = ActionRecommender()
    profile = _make_profile(last_intent="complaint")
    action = await recommender.recommend_for_customer(profile)

    assert action is not None
    assert len(action.suggested_text) > 0


# ─── 12. API 路由 /actions 返回 200 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_actions_ok(app_client):
    r = await app_client.get("/v1/dashboard/tenant_0001/actions")
    assert r.status_code == 200
    data = r.json()
    assert data["tenant_id"] == "tenant_0001"
    assert "actions" in data
    assert isinstance(data["actions"], list)
