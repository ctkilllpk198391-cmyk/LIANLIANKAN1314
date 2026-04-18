"""Dashboard v2 测试 · ≥8 用例。"""

from __future__ import annotations

import time

import pytest


# ─── helpers ─────────────────────────────────────────────────────────────────

async def _insert_suggestion(session, msg_id, tenant_id, inbound_msg_id, intent="inquiry",
                              risk="low", ts=None):
    from server.models import Suggestion as SuggestionModel
    ts = ts or int(time.time())
    session.add(SuggestionModel(
        msg_id=msg_id,
        tenant_id=tenant_id,
        inbound_msg_id=inbound_msg_id,
        intent=intent,
        risk=risk,
        text="测试回复",
        model_route="mock",
        generated_at=ts,
        similarity_check_passed=1,
        rewrite_count=0,
        forbidden_word_hit=0,
    ))


async def _insert_message(session, msg_id, tenant_id, chat_id, ts=None):
    from server.models import Message as MessageModel
    ts = ts or int(time.time())
    session.add(MessageModel(
        msg_id=msg_id,
        tenant_id=tenant_id,
        chat_id=chat_id,
        sender_id="sender_x",
        sender_name="测试用户",
        text="你好",
        msg_type="text",
        timestamp=ts,
    ))


async def _insert_review(session, msg_id, decision="accept", ts=None):
    from server.models import Review as ReviewModel
    ts = ts or int(time.time())
    session.add(ReviewModel(msg_id=msg_id, decision=decision, reviewed_at=ts))


async def _insert_customer(session, tenant_id, chat_id, vip_tier="C", last_message_at=None):
    from server.models import CustomerProfile as CustomerProfileModel
    now = int(time.time())
    last_message_at = last_message_at if last_message_at is not None else now
    try:
        session.add(CustomerProfileModel(
            tenant_id=tenant_id,
            chat_id=chat_id,
            vip_tier=vip_tier,
            last_message_at=last_message_at,
            updated_at=now,
        ))
        await session.flush()
    except Exception:
        await session.rollback()


# ─── 1. build_v2 基本结构 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_v2_basic(temp_db, loaded_tenants):
    from server.dashboard import DashboardBuilder
    db = DashboardBuilder()
    data = await db.build_v2("tenant_0001")

    assert data["tenant_id"] == "tenant_0001"
    assert "as_of" in data
    assert "today" in data
    assert "week_trend" in data
    assert "customers" in data
    assert "funnel" in data
    assert "benchmark" in data
    assert "health" in data


# ─── 2. build_v2 空租户 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_v2_empty_tenant(temp_db, loaded_tenants):
    from server.dashboard import DashboardBuilder
    db = DashboardBuilder()
    data = await db.build_v2("tenant_0001")

    # 空库：今日生成 0 · 采纳率 0
    assert data["today"]["total_generated"] == 0
    assert data["today"]["acceptance_rate"] == 0.0
    assert data["customers"]["total"] == 0
    assert data["funnel"]["inquiry"] == 0


# ─── 3. build_trend 7 天 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_trend_7days(temp_db, loaded_tenants):
    from server.dashboard import DashboardBuilder
    db = DashboardBuilder()
    trend = await db.build_trend("tenant_0001", days=7)

    assert len(trend["dates"]) == 7
    assert len(trend["acceptance_rate"]) == 7
    assert len(trend["sent_count"]) == 7
    assert len(trend["high_risk_blocked"]) == 7
    # 全空库 · 采纳率全 0
    assert all(v == 0.0 for v in trend["acceptance_rate"])


# ─── 4. build_customers tier_a 筛选 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_customers_tier_a(temp_db, loaded_tenants):
    from server.db import session_scope
    from server.dashboard import DashboardBuilder

    async with session_scope() as session:
        await _insert_customer(session, "tenant_0001", "chat_a1", vip_tier="A")
        await _insert_customer(session, "tenant_0001", "chat_b1", vip_tier="B")
        await _insert_customer(session, "tenant_0001", "chat_c1", vip_tier="C")

    db = DashboardBuilder()
    result = await db.build_customers("tenant_0001", tier="A")

    # tier=A 筛选时 · total 只数 A 层
    assert result["tier_a"] == 1
    assert result["tier_b"] == 0
    assert result["tier_c"] == 0


# ─── 5. build_customers 沉睡 30d ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_customers_sleeping_30d(temp_db, loaded_tenants):
    from server.db import session_scope
    from server.dashboard import DashboardBuilder

    now = int(time.time())
    stale_ts = now - 35 * 86400   # 35 天前 · 超过 30 天阈值
    active_ts = now - 5 * 86400   # 5 天前 · 未超

    async with session_scope() as session:
        await _insert_customer(session, "tenant_0001", "chat_stale1", vip_tier="C", last_message_at=stale_ts)
        await _insert_customer(session, "tenant_0001", "chat_stale2", vip_tier="C", last_message_at=stale_ts)
        await _insert_customer(session, "tenant_0001", "chat_active1", vip_tier="B", last_message_at=active_ts)

    db = DashboardBuilder()
    result = await db.build_customers("tenant_0001")

    stale = result["stale_30d_alert"]
    assert "chat_stale1" in stale
    assert "chat_stale2" in stale
    assert "chat_active1" not in stale


# ─── 6. build_funnel 转化率 ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_funnel_rates(temp_db, loaded_tenants):
    from server.db import session_scope
    from server.dashboard import DashboardBuilder

    async with session_scope() as session:
        # 先插入 messages 作为 inbound_msg_id 的 FK
        for i in range(10):
            await _insert_message(session, f"m{i}", "tenant_0001", "chat_x")
        # 10 inquiry · 5 negotiation · 2 order · 1 repurchase
        for i in range(10):
            await _insert_suggestion(session, f"sug_inq{i}", "tenant_0001", f"m{i}", intent="inquiry")
        for i in range(5):
            await _insert_suggestion(session, f"sug_neg{i}", "tenant_0001", f"m{i}", intent="negotiation")
        for i in range(2):
            await _insert_suggestion(session, f"sug_ord{i}", "tenant_0001", f"m{i}", intent="order")
        await _insert_suggestion(session, "sug_rep0", "tenant_0001", "m0", intent="repurchase")

    db = DashboardBuilder()
    funnel = await db.build_funnel("tenant_0001")

    assert funnel["inquiry"] == 10
    assert funnel["negotiation"] == 5
    assert funnel["order"] == 2
    assert funnel["repurchase"] == 1
    assert funnel["rates"]["inq_to_neg"] == round(5 / 10, 3)
    assert funnel["rates"]["neg_to_order"] == round(2 / 5, 3)
    assert funnel["rates"]["order_to_rep"] == round(1 / 2, 3)


# ─── 7. build_benchmark 静态基线 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_build_benchmark_static_baseline(temp_db, loaded_tenants):
    from server.dashboard import DashboardBuilder
    db = DashboardBuilder()
    bench = await db.build_benchmark("tenant_0001")

    # 静态基线验证
    assert bench["industry_p50"] == 0.65
    assert bench["industry_p90"] == 0.85
    assert "your_acceptance_rate" in bench
    assert "delta_pct" in bench
    assert bench["industry"] == "微商"


# ─── 8. weekly_report markdown 渲染 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_report_markdown_renders(temp_db, loaded_tenants):
    from server.weekly_report import WeeklyReportBuilder
    builder = WeeklyReportBuilder()
    md = await builder.build_markdown("tenant_0001")

    assert "周报" in md
    assert "tenant_0001" in md
    assert "采纳率" in md
    assert "成交漏斗" in md
    assert "同行对标" in md


# ─── 9. API 路由 /v2 返回 200 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_dashboard_v2_ok(app_client):
    r = await app_client.get("/v1/dashboard/tenant_0001/v2")
    assert r.status_code == 200
    data = r.json()
    assert data["tenant_id"] == "tenant_0001"
    assert "week_trend" in data


# ─── 10. API 路由全覆盖 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_all_new_routes(app_client):
    tid = "tenant_0001"

    r = await app_client.get(f"/v1/dashboard/{tid}/trend?days=7")
    assert r.status_code == 200
    assert "dates" in r.json()

    r = await app_client.get(f"/v1/dashboard/{tid}/customers")
    assert r.status_code == 200
    assert "total" in r.json()

    r = await app_client.get(f"/v1/dashboard/{tid}/customers?tier=A")
    assert r.status_code == 200

    r = await app_client.get(f"/v1/dashboard/{tid}/funnel")
    assert r.status_code == 200
    assert "rates" in r.json()

    r = await app_client.get(f"/v1/dashboard/{tid}/benchmark")
    assert r.status_code == 200
    assert "industry_p50" in r.json()

    r = await app_client.post(f"/v1/dashboard/{tid}/weekly_report/send")
    assert r.status_code == 200
    assert r.json()["ok"] is True
