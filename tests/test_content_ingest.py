"""T1 · 内容摄入引擎测试。"""

from __future__ import annotations

import pytest

from server.content_ingest import (
    SUPPORTED_EXTS,
    ContentIngestEngine,
    ContentRecord,
    heuristic_tag,
)
from server.embedder import BGEEmbedder
from server.knowledge_base import KnowledgeBase


def _kb():
    return KnowledgeBase(embedder=BGEEmbedder(mock=True))


# ─── 启发式分类 ──────────────────────────────────────────────────────────

def test_heuristic_tag_product():
    assert heuristic_tag("玉兰油新品介绍.md", "玉兰油精华上新") == "产品"


def test_heuristic_tag_activity():
    assert heuristic_tag("双11预热.txt", "") == "活动"


def test_heuristic_tag_feedback():
    assert heuristic_tag("客户晒单.md", "好评收集") == "反馈"


def test_heuristic_tag_other_default():
    assert heuristic_tag("foo.txt", "完全无关内容") == "其他"


def test_heuristic_tag_price():
    assert heuristic_tag("价格表.csv", "") == "价格"


# ─── 文本格式 ingest ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_md_file(temp_db):
    eng = ContentIngestEngine(knowledge_base=_kb())
    text = "# 玉兰油精华\n价格 ¥299 · 30ml · 适合 25+\n\n## 卖点\n滋润 · 紧致"
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="新品.md",
        file_bytes=text.encode("utf-8"),
    )
    assert record.parsed_chunks > 0
    assert record.source_tag in ("产品", "活动", "其他")
    assert record.file_type == "text"


@pytest.mark.asyncio
async def test_ingest_csv_file(temp_db):
    eng = ContentIngestEngine(knowledge_base=_kb())
    csv_text = "name,price,stock\n精华,299,5\n面霜,199,10\n洗面奶,49,30"
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="价格表.csv",
        file_bytes=csv_text.encode("utf-8"),
    )
    assert record.parsed_chunks == 4   # csv 每行一 chunk（含 header）
    assert record.file_type == "csv"
    assert record.source_tag == "价格"


@pytest.mark.asyncio
async def test_ingest_image_with_vlm_mock(temp_db):
    class MockVLM:
        async def describe(self, image_url, prompt=None):
            return "一张玉兰油精华产品图 · 紫色包装 · 30ml"

    eng = ContentIngestEngine(knowledge_base=_kb(), vlm_client=MockVLM())
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="产品图.jpg",
        file_bytes=b"fake_image_bytes",
    )
    assert record.parsed_chunks > 0
    assert record.file_type == "image"


@pytest.mark.asyncio
async def test_ingest_image_without_vlm_no_chunks(temp_db):
    eng = ContentIngestEngine(knowledge_base=_kb(), vlm_client=None)
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="产品图.jpg",
        file_bytes=b"fake",
    )
    # text 是占位 · KB 仍能 ingest 但小
    assert record.file_type == "image"


@pytest.mark.asyncio
async def test_ingest_audio_with_asr_mock(temp_db):
    class MockASR:
        async def transcribe(self, voice_url, lang="zh"):
            return "我今天给大家介绍我们家爆款 · 玉兰油精华"

    eng = ContentIngestEngine(knowledge_base=_kb(), asr_client=MockASR())
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="老板讲解.mp3",
        file_bytes=b"fake",
    )
    assert record.file_type == "audio_video"
    assert record.parsed_chunks > 0


# ─── LLM 自动分类（mock） ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_classify_llm_returns_valid_tag(temp_db):
    class MockLLM:
        async def respond(self, **kwargs):
            return "产品"

    eng = ContentIngestEngine(knowledge_base=_kb(), llm_client=MockLLM())
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="x.md",
        file_bytes=b"some content",
    )
    assert record.source_tag == "产品"


@pytest.mark.asyncio
async def test_classify_llm_invalid_falls_back_heuristic(temp_db):
    class BadLLM:
        async def respond(self, **kwargs):
            return "完全不是有效分类"

    eng = ContentIngestEngine(knowledge_base=_kb(), llm_client=BadLLM())
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="新品玉兰油.md",
        file_bytes="产品介绍".encode("utf-8"),
    )
    # LLM 返回无效 · fallback heuristic → "产品"（关键词命中）
    assert record.source_tag == "产品"


# ─── 下游触发：marketing_plan ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_downstream_marketing_triggered_for_product(temp_db):
    triggered = []

    class MockMarketing:
        async def generate(self, tenant_id, source_content_id, source_text):
            triggered.append(source_content_id)
            return f"plan_{source_content_id[:8]}"

    eng = ContentIngestEngine(
        knowledge_base=_kb(),
        marketing_plan_generator=MockMarketing(),
    )
    record = await eng.ingest(
        tenant_id="tenant_0001",
        file_name="新品介绍.md",
        file_bytes="产品 X 上新 ¥299 玉兰油精华".encode("utf-8"),
    )
    assert len(triggered) == 1
    assert record.marketing_plan_id is not None


@pytest.mark.asyncio
async def test_downstream_marketing_not_triggered_for_feedback(temp_db):
    triggered = []

    class MockMarketing:
        async def generate(self, tenant_id, source_content_id, source_text):
            triggered.append(source_content_id)
            return "plan_xxx"

    eng = ContentIngestEngine(
        knowledge_base=_kb(),
        marketing_plan_generator=MockMarketing(),
    )
    await eng.ingest(
        tenant_id="tenant_0001",
        file_name="客户反馈截图说明.md",
        file_bytes="客户晒单 反馈".encode("utf-8"),
    )
    # source_tag=反馈 · 不在 downstream_tags · 不触发
    assert triggered == []


def test_supported_exts_complete():
    """常见格式都在支持范围。"""
    for ext in [".md", ".txt", ".csv", ".docx", ".jpg", ".png", ".mp3", ".mp4"]:
        assert ext in SUPPORTED_EXTS


def test_content_record_dataclass_default_lists():
    r = ContentRecord(
        file_id="x", tenant_id="t", file_name="f", file_type="text",
        size_bytes=10, parsed_chunks=2, source_tag="产品",
    )
    assert r.knowledge_chunk_ids == []
    assert r.marketing_plan_id is None
