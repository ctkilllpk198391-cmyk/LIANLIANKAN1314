"""服务端 risk_check · 禁用词 + 相似度 + 去重。"""

from __future__ import annotations

import time

import pytest

from server.risk_check import (
    contains_forbidden_word,
    is_duplicate,
    text_similarity,
)


def test_forbidden_word_hit():
    hit, words = contains_forbidden_word("我保证给您退款")
    assert hit is True
    assert "保证" in words


def test_forbidden_word_clean():
    hit, words = contains_forbidden_word("好的，稍等我看看")
    assert hit is False
    assert words == []


def test_text_similarity_identical():
    assert text_similarity("hello", "hello") == 1.0


def test_text_similarity_different():
    assert text_similarity("hello", "goodbye") < 0.5


def test_text_similarity_empty():
    assert text_similarity("", "x") == 0.0


@pytest.mark.asyncio
async def test_is_duplicate_with_no_history(temp_db):
    result = await is_duplicate("全新内容", "tenant_0001")
    assert result is False


@pytest.mark.asyncio
async def test_is_duplicate_detects_recent(temp_db, loaded_tenants):
    """插入一条 suggestion · 第二条相似度 > 0.6 返回 True。"""
    from server.db import session_scope
    from server.models import Message, Suggestion

    async with session_scope() as session:
        session.add(
            Message(
                msg_id="in_1",
                tenant_id="tenant_0001",
                chat_id="c1",
                sender_id="s1",
                text="hi",
                timestamp=int(time.time()),
            )
        )
        session.add(
            Suggestion(
                msg_id="sug_1",
                tenant_id="tenant_0001",
                inbound_msg_id="in_1",
                intent="greeting",
                risk="low",
                text="您好，欢迎光临，有什么需要的吗？",
                model_route="hermes_default",
                generated_at=int(time.time()),
            )
        )

    dup = await is_duplicate("您好，欢迎光临，有什么需要的吗", "tenant_0001")
    assert dup is True

    not_dup = await is_duplicate("完全不一样的另一种打招呼方式呢", "tenant_0001")
    assert not_dup is False
