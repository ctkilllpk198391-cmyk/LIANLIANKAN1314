"""F3 · 知识库 RAG 测试。"""

from __future__ import annotations

import pytest

from server.embedder import BGEEmbedder
from server.knowledge_base import KnowledgeBase, split_into_chunks


def _kb():
    return KnowledgeBase(embedder=BGEEmbedder(mock=True))


def test_split_paragraphs():
    text = "段落一。\n\n段落二。\n\n段落三。"
    chunks = split_into_chunks(text, 300)
    assert len(chunks) == 3


def test_split_long_paragraph_by_sentences():
    long_para = "句子A。" * 100
    chunks = split_into_chunks(long_para, 50)
    assert len(chunks) > 1
    assert all(len(c) <= 100 for c in chunks)  # 略超是允许的（保完整句）


def test_split_csv_one_per_line():
    text = "name,price,stock\n精华,299,5\n面霜,199,10"
    chunks = split_into_chunks(text)
    assert len(chunks) == 3
    assert "精华" in chunks[1]


def test_split_markdown_table_kept_whole():
    text = "正文。\n\n| 项 | 值 |\n|---|---|\n| A | 1 |\n| B | 2 |"
    chunks = split_into_chunks(text)
    table = next((c for c in chunks if "|" in c), None)
    assert table is not None and table.count("|") >= 4


def test_split_empty():
    assert split_into_chunks("") == []
    assert split_into_chunks("   ") == []


@pytest.mark.asyncio
async def test_ingest_basic(temp_db):
    kb = _kb()
    n = await kb.ingest("tenant_0001", "products.md", "产品 A 介绍。\n\n产品 B 介绍。")
    assert n == 2

    stats = await kb.stats("tenant_0001")
    assert stats["total_chunks"] == 2
    assert stats["sources"]["products.md"] == 2


@pytest.mark.asyncio
async def test_query_top_k(temp_db):
    kb = _kb()
    await kb.ingest("tenant_0001", "products.md",
                    "玉兰油精华 299 元。\n\n面霜 199 元。\n\n洗面奶 49 元。")
    results = await kb.query("tenant_0001", "玉兰油精华 299 元", top_k=2, min_score=0.0)
    assert len(results) <= 2
    assert results[0].text.startswith("玉兰油")  # mock embedder 同文本最高


@pytest.mark.asyncio
async def test_query_min_score_filter(temp_db):
    kb = _kb()
    await kb.ingest("tenant_0001", "x.md", "完全不相关内容")
    # mock embedder 不同文本 cosine 通常很低 · 高 min_score 过滤掉
    results = await kb.query("tenant_0001", "另外一个完全不同的查询", top_k=5, min_score=0.95)
    assert results == []


@pytest.mark.asyncio
async def test_query_empty_text(temp_db):
    kb = _kb()
    await kb.ingest("tenant_0001", "x.md", "内容")
    assert await kb.query("tenant_0001", "") == []
    assert await kb.query("tenant_0001", "   ") == []


@pytest.mark.asyncio
async def test_query_no_chunks_for_tenant(temp_db):
    kb = _kb()
    await kb.ingest("tenant_0001", "x.md", "tenant 1 内容")
    results = await kb.query("tenant_0002", "查询", top_k=5)
    assert results == []  # tenant 2 无数据


@pytest.mark.asyncio
async def test_delete_source(temp_db):
    kb = _kb()
    await kb.ingest("tenant_0001", "v1.md", "段一。\n\n段二。")
    await kb.ingest("tenant_0001", "v2.md", "其他内容。")
    n = await kb.delete_source("tenant_0001", "v1.md")
    assert n == 2

    stats = await kb.stats("tenant_0001")
    assert "v1.md" not in stats["sources"]
    assert stats["sources"].get("v2.md") == 1


@pytest.mark.asyncio
async def test_render_for_prompt():
    from server.knowledge_base import ChunkResult

    chunks = [
        ChunkResult(chunk_id=1, source="products.md", text="玉兰油精华 299 元", score=0.92, tags=[]),
        ChunkResult(chunk_id=2, source="price.csv", text="面霜 199 元", score=0.81, tags=[]),
    ]
    out = KnowledgeBase.render_for_prompt(chunks)
    assert "玉兰油" in out
    assert "面霜" in out
    assert "products.md" in out


def test_render_for_prompt_empty():
    assert KnowledgeBase.render_for_prompt([]) == ""


@pytest.mark.asyncio
async def test_tenant_isolation_in_query(temp_db):
    kb = _kb()
    await kb.ingest("tenant_0001", "a.md", "tenant1 价格表")
    await kb.ingest("tenant_0002", "b.md", "tenant2 完全不同的内容")
    r1 = await kb.query("tenant_0001", "tenant1 价格表", top_k=5, min_score=0.0)
    sources = {x.source for x in r1}
    assert "b.md" not in sources
