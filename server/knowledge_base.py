"""F3 · 知识库 RAG · ingest + query + delete · 多租户隔离。

数据流：
  老板上传 markdown/txt/csv → ingest 切 chunk → embedder.encode → 存 knowledge_chunks
  客户问产品 → query(text) → 全表 cosine top_k → 拼 prompt 给 generator
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import delete, select

from server.db import session_scope
from server.embedder import BGEEmbedder, cosine, get_default_embedder
from server.models import KnowledgeChunk

logger = logging.getLogger(__name__)


@dataclass
class ChunkResult:
    chunk_id: int
    source: str
    text: str
    score: float
    tags: list[str]


class KnowledgeBase:
    """多租户知识库 · 全表 cosine 召回（早期 <1000 chunk 性能足够）。"""

    def __init__(self, embedder: Optional[BGEEmbedder] = None, chunk_size: int = 300):
        self.embedder = embedder or get_default_embedder()
        self.chunk_size = chunk_size

    async def ingest(
        self,
        tenant_id: str,
        source: str,
        text: str,
        tags: Optional[list[str]] = None,
    ) -> int:
        """切 chunk + 算 embedding + 写库。返回写入 chunk 数量。"""
        chunks = split_into_chunks(text, self.chunk_size)
        if not chunks:
            return 0

        embeddings = self.embedder.encode_batch(chunks)
        tags_json = json.dumps(tags or [], ensure_ascii=False)
        now = int(time.time())

        async with session_scope() as session:
            for chunk_text, vec in zip(chunks, embeddings):
                session.add(
                    KnowledgeChunk(
                        tenant_id=tenant_id,
                        source=source,
                        chunk_text=chunk_text,
                        embedding=json.dumps(vec),
                        tags=tags_json,
                        created_at=now,
                    )
                )
        return len(chunks)

    async def query(
        self,
        tenant_id: str,
        query_text: str,
        top_k: int = 3,
        min_score: float = 0.3,
    ) -> list[ChunkResult]:
        """全表 cosine 召回 top_k · score < min_score 过滤。"""
        if not query_text.strip():
            return []

        query_vec = self.embedder.encode(query_text)

        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(KnowledgeChunk)
                    .where(KnowledgeChunk.tenant_id == tenant_id)
                )
            ).scalars().all()

        if not rows:
            return []

        scored: list[ChunkResult] = []
        for row in rows:
            try:
                vec = json.loads(row.embedding)
            except (json.JSONDecodeError, TypeError):
                continue
            score = cosine(query_vec, vec)
            if score >= min_score:
                scored.append(
                    ChunkResult(
                        chunk_id=row.id,
                        source=row.source,
                        text=row.chunk_text,
                        score=score,
                        tags=_safe_loads_list(row.tags),
                    )
                )

        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    async def delete_source(self, tenant_id: str, source: str) -> int:
        """删除指定 source 的所有 chunk · 返回删除数量。"""
        async with session_scope() as session:
            result = await session.execute(
                delete(KnowledgeChunk)
                .where(KnowledgeChunk.tenant_id == tenant_id)
                .where(KnowledgeChunk.source == source)
            )
            return result.rowcount or 0

    async def stats(self, tenant_id: str) -> dict:
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(KnowledgeChunk.source).where(KnowledgeChunk.tenant_id == tenant_id)
                )
            ).scalars().all()
        sources: dict[str, int] = {}
        for s in rows:
            sources[s] = sources.get(s, 0) + 1
        return {"total_chunks": len(rows), "sources": sources}

    @staticmethod
    def render_for_prompt(chunks: list[ChunkResult]) -> str:
        """召回结果拼成 prompt 用的"知识库参考"块。"""
        if not chunks:
            return ""
        lines = ["【知识库参考】（按相关度排）"]
        for i, c in enumerate(chunks, 1):
            text = c.text.strip().replace("\n", " ")
            if len(text) > 200:
                text = text[:200] + "..."
            lines.append(f"{i}. [{c.source}] {text}")
        return "\n".join(lines)


def split_into_chunks(text: str, chunk_size: int = 300) -> list[str]:
    """段（\\n\\n）→ 句号细切 · markdown 表格保留整行 · csv 每行一 chunk。"""
    if not text or not text.strip():
        return []

    # CSV 启发：检测全文含逗号且第一行像 header → 每行一 chunk
    lines = text.strip().split("\n")
    if len(lines) > 1 and all("," in ln for ln in lines[:5]):
        return [ln.strip() for ln in lines if ln.strip()]

    chunks: list[str] = []
    paragraphs = re.split(r"\n\s*\n", text.strip())
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        # markdown 表格行不再切
        if "|" in para and para.count("|") >= 2:
            chunks.append(para)
            continue
        if len(para) <= chunk_size:
            chunks.append(para)
            continue
        sentences = re.split(r"(?<=[。！？!?\.])", para)
        buf = ""
        for sent in sentences:
            if not sent:
                continue
            if len(buf) + len(sent) > chunk_size:
                if buf:
                    chunks.append(buf.strip())
                buf = sent
            else:
                buf += sent
        if buf.strip():
            chunks.append(buf.strip())

    return [c for c in chunks if c.strip()]


def _safe_loads_list(s: Optional[str]) -> list:
    if not s:
        return []
    try:
        v = json.loads(s)
        return v if isinstance(v, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
