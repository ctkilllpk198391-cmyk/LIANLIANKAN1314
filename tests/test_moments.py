"""S8 · 朋友圈托管测试 · ≥8 用例。"""

from __future__ import annotations

import time

import pytest

from server.moments_manager import MomentsManager
from server.models import MomentsPost
from server.db import session_scope
from sqlalchemy import select


# ── mock llm_client ──────────────────────────────────────────────────────────

class _MockLLM:
    """返回固定字符串的 mock LLM。"""

    async def respond(self, prompt, tenant_id, model_route, max_tokens=300, system=None, **kwargs):
        return f"[llm mock] {prompt[:30]}"


# ── 用例 ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_post_returns_string(temp_db):
    """generate_post 返回非空字符串。"""
    mgr = MomentsManager(llm_client=_MockLLM())
    text = await mgr.generate_post("tenant_0001", "product")
    assert isinstance(text, str)
    assert len(text) > 0


@pytest.mark.asyncio
async def test_generate_post_unknown_type_raises(temp_db):
    """未知 post_type 抛 ValueError。"""
    mgr = MomentsManager(llm_client=_MockLLM())
    with pytest.raises(ValueError, match="unknown post_type"):
        await mgr.generate_post("tenant_0001", "unknown_type")


@pytest.mark.asyncio
async def test_schedule_daily_creates_3(temp_db):
    """schedule_daily 返回 3 个 post_id · 状态均为 scheduled。"""
    mgr = MomentsManager(llm_client=_MockLLM())
    ids = await mgr.schedule_daily("tenant_0001")
    assert len(ids) == 3
    for pid in ids:
        assert pid.startswith("mp_")

    posts = await mgr.list_posts("tenant_0001", status="scheduled")
    assert len(posts) == 3


@pytest.mark.asyncio
async def test_list_posts_filters_by_status(temp_db):
    """list_posts status 过滤正常工作。"""
    mgr = MomentsManager(llm_client=_MockLLM())

    # 写一条 draft
    content = await mgr.generate_post("tenant_0001", "lifestyle")
    await mgr._save_post("tenant_0001", "lifestyle", content, status="draft")

    # 写一条 scheduled
    content2 = await mgr.generate_post("tenant_0001", "product")
    await mgr._save_post("tenant_0001", "product", content2, status="scheduled",
                         scheduled_at=int(time.time()) + 3600)

    drafts = await mgr.list_posts("tenant_0001", status="draft")
    assert len(drafts) == 1
    assert drafts[0]["status"] == "draft"

    scheduled = await mgr.list_posts("tenant_0001", status="scheduled")
    assert len(scheduled) == 1
    assert scheduled[0]["status"] == "scheduled"

    all_posts = await mgr.list_posts("tenant_0001")
    assert len(all_posts) == 2


@pytest.mark.asyncio
async def test_cancel_pending(temp_db):
    """cancel 将 draft/scheduled 变为 cancelled · 重复 cancel 返回 False。"""
    mgr = MomentsManager(llm_client=_MockLLM())
    content = await mgr.generate_post("tenant_0001", "promo")
    pid = await mgr._save_post("tenant_0001", "promo", content, status="draft")

    assert await mgr.cancel(pid) is True
    assert await mgr.cancel(pid) is False  # 已是 cancelled

    posts = await mgr.list_posts("tenant_0001", status="cancelled")
    assert len(posts) == 1


@pytest.mark.asyncio
async def test_publish_marks_status(temp_db):
    """publish 将 draft 标记为 published · published_at 有值。"""
    mgr = MomentsManager(llm_client=_MockLLM())
    content = await mgr.generate_post("tenant_0001", "feedback")
    pid = await mgr._save_post("tenant_0001", "feedback", content, status="draft")

    ok = await mgr.publish(pid)
    assert ok is True

    posts = await mgr.list_posts("tenant_0001", status="published")
    assert len(posts) == 1
    assert posts[0]["published_at"] is not None


@pytest.mark.asyncio
async def test_tick_picks_due_posts(temp_db):
    """tick 扫到期的 scheduled posts 并 publish。"""
    mgr = MomentsManager(llm_client=_MockLLM())

    # 写一条过期的 scheduled
    content = await mgr.generate_post("tenant_0001", "product")
    pid = await mgr._save_post(
        "tenant_0001", "product", content,
        status="scheduled",
        scheduled_at=int(time.time()) - 3600,  # 1 小时前
    )

    # 写一条未来的 scheduled（不应触发）
    content2 = await mgr.generate_post("tenant_0001", "lifestyle")
    pid2 = await mgr._save_post(
        "tenant_0001", "lifestyle", content2,
        status="scheduled",
        scheduled_at=int(time.time()) + 3600,  # 1 小时后
    )

    n = await mgr.tick()
    assert n == 1

    posts_published = await mgr.list_posts("tenant_0001", status="published")
    assert len(posts_published) == 1
    assert posts_published[0]["post_id"] == pid

    posts_scheduled = await mgr.list_posts("tenant_0001", status="scheduled")
    assert len(posts_scheduled) == 1
    assert posts_scheduled[0]["post_id"] == pid2


def test_post_types_have_prompts():
    """4 种 post_type 全部在 POST_PROMPTS 中。"""
    required = {"product", "feedback", "promo", "lifestyle"}
    assert required == set(MomentsManager.POST_PROMPTS.keys())


@pytest.mark.asyncio
async def test_generate_post_no_llm_returns_mock(temp_db):
    """无 llm_client 时返回 mock 字符串（不崩溃）。"""
    mgr = MomentsManager(llm_client=None)
    text = await mgr.generate_post("tenant_0001", "lifestyle")
    assert "[mock lifestyle]" in text


@pytest.mark.asyncio
async def test_publish_triggers_ws_push(temp_db):
    """publish 时触发 ws_push 回调，payload 包含 moments_post_command 类型。"""
    pushed = []

    async def fake_push(tenant_id, payload):
        pushed.append((tenant_id, payload))

    mgr = MomentsManager(llm_client=_MockLLM(), ws_push=fake_push)
    content = await mgr.generate_post("tenant_0001", "product")
    pid = await mgr._save_post("tenant_0001", "product", content, status="draft")

    await mgr.publish(pid)

    assert len(pushed) == 1
    tenant_id_pushed, payload = pushed[0]
    assert tenant_id_pushed == "tenant_0001"
    assert payload["type"] == "moments_post_command"
    assert payload["post_id"] == pid
