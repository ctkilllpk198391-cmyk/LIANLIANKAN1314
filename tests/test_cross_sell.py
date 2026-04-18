"""S7 · CrossSellEngine 单元测试 · 全 mock · ≥6 用例。"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.cross_sell import CrossSellEngine, ProductRec, _format_suffix
from shared.types import IntentEnum


# ── Mock 辅助 ─────────────────────────────────────────────────────────────────

def _make_profile(
    purchase_history: list[dict] | None = None,
    tags: list[str] | None = None,
    days_since_last: Optional[int] = 5,
    chat_id: str = "chat_001",
    tenant_id: str = "tenant_001",
):
    """构造轻量 CustomerProfileSnapshot mock。"""
    profile = MagicMock()
    profile.tenant_id = tenant_id
    profile.chat_id = chat_id
    profile.purchase_history = purchase_history or []
    profile.tags = tags or []
    profile.days_since_last = days_since_last
    return profile


def _make_kb(chunks: list | None = None):
    """构造 KnowledgeBase mock，返回指定 chunks。"""
    kb = MagicMock()
    kb.query = AsyncMock(return_value=chunks or [])
    return kb


def _make_chunk(text: str, score: float = 0.8):
    """构造 ChunkResult mock。"""
    chunk = MagicMock()
    chunk.text = text
    chunk.score = score
    return chunk


# ── 用例 1：有购买历史时成功返回推荐 ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_recommend_with_purchase_history():
    """有购买历史 + KB 有相关 chunk → 返回 1-2 个 ProductRec。"""
    purchase_history = [
        {"date": int(time.time()) - 86400, "sku": "face_cream_a", "amount": 199.0},
        {"date": int(time.time()) - 172800, "sku": "serum_b", "amount": 299.0},
    ]
    profile = _make_profile(purchase_history=purchase_history)
    chunks = [
        _make_chunk("# NewSerum-X 精华液\n适合敏感肌，修护效果好。", score=0.9),
        _make_chunk("# MoistureCream-Y 保湿霜\n深层补水，持久不油腻。", score=0.75),
    ]
    kb = _make_kb(chunks)
    engine = CrossSellEngine(knowledge_base=kb)

    recs = await engine.recommend(
        tenant_id="tenant_001",
        customer_profile=profile,
        current_intent=IntentEnum.INQUIRY,
        last_message_text="这款精华怎么样",
    )

    assert len(recs) >= 1
    assert all(isinstance(r, ProductRec) for r in recs)
    assert all(r.sku for r in recs)
    assert all(r.score > 0 for r in recs)


# ── 用例 2：COMPLAINT intent → 不推荐 ────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_recommend_for_complaint():
    """intent=COMPLAINT 时，直接返回空列表，不查 KB。"""
    purchase_history = [{"date": int(time.time()), "sku": "item_x", "amount": 100.0}]
    profile = _make_profile(purchase_history=purchase_history)
    kb = _make_kb([_make_chunk("# ProductY\n好产品。", score=0.9)])
    engine = CrossSellEngine(knowledge_base=kb)

    recs = await engine.recommend(
        tenant_id="tenant_001",
        customer_profile=profile,
        current_intent=IntentEnum.COMPLAINT,
        last_message_text="这个东西质量太差了",
    )

    assert recs == []
    # KB 不应被查询
    kb.query.assert_not_called()


# ── 用例 3：SENSITIVE intent → 不推荐 ────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_recommend_for_sensitive_intent():
    """intent=SENSITIVE 时同样不推。"""
    purchase_history = [{"date": int(time.time()), "sku": "item_a", "amount": 50.0}]
    profile = _make_profile(purchase_history=purchase_history)
    kb = _make_kb([_make_chunk("# ProductZ\n描述。", score=0.85)])
    engine = CrossSellEngine(knowledge_base=kb)

    recs = await engine.recommend(
        tenant_id="tenant_001",
        customer_profile=profile,
        current_intent=IntentEnum.SENSITIVE,
        last_message_text="",
    )

    assert recs == []
    kb.query.assert_not_called()


# ── 用例 4：休眠客户（30 天未联系）→ 不推荐 ──────────────────────────────────
@pytest.mark.asyncio
async def test_no_recommend_for_dormant_customer():
    """days_since_last >= 30 的休眠客户不做交叉销售。"""
    purchase_history = [{"date": int(time.time()) - 40 * 86400, "sku": "old_item", "amount": 88.0}]
    profile = _make_profile(purchase_history=purchase_history, days_since_last=35)
    kb = _make_kb([_make_chunk("# NewProduct\n新品。", score=0.9)])
    engine = CrossSellEngine(knowledge_base=kb)

    recs = await engine.recommend(
        tenant_id="tenant_001",
        customer_profile=profile,
        current_intent=IntentEnum.INQUIRY,
        last_message_text="你们有什么新品",
    )

    assert recs == []
    kb.query.assert_not_called()


# ── 用例 5：当天已推过同 chat → maybe_append 不再插入 ────────────────────────
@pytest.mark.asyncio
async def test_max_one_per_day_per_chat():
    """同 (tenant_id, chat_id) 当天第 2 次调用 maybe_append → 原样返回。"""
    engine = CrossSellEngine(knowledge_base=None, max_per_day_per_chat=1)
    recs = [ProductRec(sku="prod_a", name="精华A", reason="相关", score=0.9)]

    original = "好的，这款很受欢迎哦~"

    # 第 1 次：应该插入
    result1 = await engine.maybe_append_to_reply(
        original_reply=original,
        recs=recs,
        chat_id="chat_999",
        tenant_id="tenant_001",
    )
    assert result1 != original  # 已插入推荐

    # 第 2 次同 chat 同天：不应再插入
    result2 = await engine.maybe_append_to_reply(
        original_reply=original,
        recs=recs,
        chat_id="chat_999",
        tenant_id="tenant_001",
    )
    assert result2 == original  # 原样返回


# ── 用例 6：maybe_append 插入自然话术 ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_maybe_append_inserts_naturally():
    """maybe_append_to_reply 插入时，话术自然，不是硬广告。"""
    engine = CrossSellEngine(knowledge_base=None)
    recs = [ProductRec(sku="serum_c", name="修护精华C", reason="适合您肤质", score=0.88)]
    original = "这款面霜用过的反馈都不错哦~"

    result = await engine.maybe_append_to_reply(
        original_reply=original,
        recs=recs,
        chat_id="chat_100",
        tenant_id="tenant_002",
    )

    # 结果包含原始回复
    assert original.strip() in result
    # 包含推荐产品名
    assert "修护精华C" in result
    # 话术里包含自然衔接词
    assert any(kw in result for kw in ["对了", "你之前", "适合", "看看"])
    # 没有硬广告词
    assert "立即购买" not in result
    assert "限时折扣" not in result


# ── 用例 7：推荐按 score 降序排列 ─────────────────────────────────────────────
@pytest.mark.asyncio
async def test_recommendation_score_ordering():
    """多个候选产品按 score 从高到低返回。"""
    purchase_history = [{"date": int(time.time()), "sku": "base_item", "amount": 120.0}]
    profile = _make_profile(purchase_history=purchase_history, days_since_last=2)
    chunks = [
        _make_chunk("# ProductLow-L 低分产品\n描述L。", score=0.4),
        _make_chunk("# ProductHigh-H 高分产品\n描述H。", score=0.95),
        _make_chunk("# ProductMid-M 中分产品\n描述M。", score=0.7),
    ]
    kb = _make_kb(chunks)
    engine = CrossSellEngine(knowledge_base=kb)

    recs = await engine.recommend(
        tenant_id="tenant_001",
        customer_profile=profile,
        current_intent=IntentEnum.ORDER,
        last_message_text="",
    )

    assert len(recs) >= 1
    # 第一个推荐 score 应 >= 后续
    for i in range(len(recs) - 1):
        assert recs[i].score >= recs[i + 1].score


# ── 用例 8：无购买历史 → 返回空 ───────────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_recommend_without_purchase_history():
    """purchase_history 为空时，不推荐任何产品。"""
    profile = _make_profile(purchase_history=[], days_since_last=2)
    kb = _make_kb([_make_chunk("# SomeProduct\n好产品。", score=0.9)])
    engine = CrossSellEngine(knowledge_base=kb)

    recs = await engine.recommend(
        tenant_id="tenant_001",
        customer_profile=profile,
        current_intent=IntentEnum.INQUIRY,
        last_message_text="有什么推荐",
    )

    assert recs == []


# ── 用例 9：不同 chat 的每日限制相互独立 ─────────────────────────────────────
@pytest.mark.asyncio
async def test_daily_limit_per_chat_is_independent():
    """chat_A 推过不影响 chat_B 的配额。"""
    engine = CrossSellEngine(knowledge_base=None, max_per_day_per_chat=1)
    recs = [ProductRec(sku="prod_x", name="产品X", reason="适合", score=0.9)]
    original = "好的~"

    # chat_A 推一次
    await engine.maybe_append_to_reply(original, recs, "chat_A", "tenant_001")

    # chat_B 首次，应能插入
    result_b = await engine.maybe_append_to_reply(original, recs, "chat_B", "tenant_001")
    assert "产品X" in result_b


# ── 用例 10：maybe_append 无推荐时原样返回 ───────────────────────────────────
@pytest.mark.asyncio
async def test_maybe_append_no_recs_returns_original():
    """recs 为空列表时，原样返回 original_reply，不修改内容。"""
    engine = CrossSellEngine(knowledge_base=None)
    original = "感谢您的购买，有问题随时联系我哦~"

    result = await engine.maybe_append_to_reply(
        original_reply=original,
        recs=[],
        chat_id="chat_200",
        tenant_id="tenant_001",
    )

    assert result == original
