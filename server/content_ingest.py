"""T1 · 内容摄入引擎 · 老板的"魔法文件夹"。

第一性原理：老板把想法/产品/活动丢进文件夹 → AI 自动消化 → 立即影响私聊 + 触发营销。

支持格式（路由）：
  .md / .txt        → 直接 KB.ingest
  .csv              → 切行 → KB.ingest（每行作为 chunk）
  .docx             → python-docx 提文本 → KB.ingest（无 docx 库时跳过）
  .jpg / .png       → vlm.describe → KB.ingest
  .mp3 / .mp4 / .m4a → asr.transcribe → KB.ingest

自动分类（source_tag）：
  - LLM 可用 → 看前 200 字推断（产品/活动/反馈/培训/价格/其他）
  - 启发式兜底：按文件名关键词
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from sqlalchemy import select

from server.db import session_scope

logger = logging.getLogger(__name__)


# ─── 文件类型分类 ───────────────────────────────────────────────────────

TEXT_EXTS = {".md", ".txt"}
DOCX_EXTS = {".docx"}
CSV_EXTS = {".csv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac"}
VIDEO_EXTS = {".mp4", ".mov", ".avi"}

SUPPORTED_EXTS = TEXT_EXTS | DOCX_EXTS | CSV_EXTS | IMAGE_EXTS | AUDIO_EXTS | VIDEO_EXTS


# ─── source_tag 启发式（无 LLM 时兜底） ────────────────────────────────

TAG_KEYWORDS = {
    "产品": ["产品", "新品", "上新", "spec", "参数", "材质", "成分"],
    "活动": ["活动", "促销", "双11", "618", "秒杀", "限时", "节日"],
    "反馈": ["反馈", "评价", "晒单", "好评", "客户说", "用户体验"],
    "培训": ["培训", "教程", "讲解", "操作", "话术", "话术库", "SOP"],
    "价格": ["价格", "报价", "折扣", "优惠", "费用", "套餐"],
}


def heuristic_tag(file_name: str, sample_text: str = "") -> str:
    haystack = (file_name + " " + sample_text[:200]).lower()
    for tag, keywords in TAG_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in haystack:
                return tag
    return "其他"


# ─── 数据契约 ────────────────────────────────────────────────────────────

@dataclass
class ContentRecord:
    file_id: str
    tenant_id: str
    file_name: str
    file_type: str
    size_bytes: int
    parsed_chunks: int
    source_tag: str
    knowledge_chunk_ids: list[int] = field(default_factory=list)
    marketing_plan_id: Optional[str] = None
    uploaded_at: int = 0


# ─── 引擎 ────────────────────────────────────────────────────────────────

class ContentIngestEngine:
    """多格式解析 + KB 入库 + 自动触发下游（marketing_plan）。"""

    def __init__(
        self,
        knowledge_base,
        vlm_client=None,
        asr_client=None,
        llm_client=None,
        marketing_plan_generator=None,
        downstream_tags: Optional[list[str]] = None,
    ):
        self.kb = knowledge_base
        self.vlm = vlm_client
        self.asr = asr_client
        self.llm = llm_client
        self.marketing = marketing_plan_generator
        self.downstream_tags = downstream_tags or ["产品", "活动"]

    async def ingest(
        self,
        tenant_id: str,
        file_name: str,
        file_bytes: bytes,
        save_record: bool = True,
    ) -> ContentRecord:
        """主入口：多格式解析 → KB 入库 → 落记录 → 触发下游。"""
        ext = Path(file_name).suffix.lower()
        size = len(file_bytes)
        file_id = f"content_{uuid.uuid4().hex[:16]}"
        now = int(time.time())

        # 1. 提取文本
        text, file_type = await self._extract_text(file_name, file_bytes, ext)

        # 2. 入 KB（如果有文本）
        chunks = 0
        if text and text.strip():
            chunks = await self.kb.ingest(
                tenant_id=tenant_id,
                source=file_name,
                text=text,
            )

        # 3. 自动分类
        source_tag = await self._classify(file_name, text)

        record = ContentRecord(
            file_id=file_id,
            tenant_id=tenant_id,
            file_name=file_name,
            file_type=file_type,
            size_bytes=size,
            parsed_chunks=chunks,
            source_tag=source_tag,
            uploaded_at=now,
        )

        # 4. 落记录
        if save_record:
            await self._save_record(record)

        # 5. 触发下游：marketing_plan 自动生成
        if (
            self.marketing
            and source_tag in self.downstream_tags
            and chunks > 0
        ):
            try:
                plan_id = await self.marketing.generate(
                    tenant_id=tenant_id,
                    source_content_id=file_id,
                    source_text=text,
                )
                record.marketing_plan_id = plan_id
                if save_record:
                    await self._update_marketing_id(file_id, plan_id)
            except Exception as e:
                logger.error("marketing trigger failed: %s", e)

        logger.info(
            "ingested tenant=%s file=%s type=%s tag=%s chunks=%d",
            tenant_id, file_name, file_type, source_tag, chunks,
        )
        return record

    # ─── 文本提取（按 ext 路由）──────────────────────────────────────────

    async def _extract_text(self, file_name: str, file_bytes: bytes, ext: str) -> tuple[str, str]:
        if ext in TEXT_EXTS:
            return file_bytes.decode("utf-8", errors="replace"), "text"

        if ext in CSV_EXTS:
            return file_bytes.decode("utf-8", errors="replace"), "csv"

        if ext in DOCX_EXTS:
            text = _extract_docx(file_bytes)
            return text, "docx"

        if ext in IMAGE_EXTS:
            if self.vlm:
                # 客户端通常上传文件 → server 落盘 → vlm 拿 url
                # 此处 mock 路径：把 file_name 作为伪 url
                desc = await self.vlm.describe(file_name)
                return f"[图片：{desc}]", "image"
            return f"[图片 {file_name} · 无 vlm · 跳过解析]", "image"

        if ext in AUDIO_EXTS or ext in VIDEO_EXTS:
            if self.asr:
                trans = await self.asr.transcribe(file_name)
                return f"[音频转写]\n{trans}", "audio_video"
            return f"[音频/视频 {file_name} · 无 asr · 跳过解析]", "audio_video"

        return "", "unknown"

    # ─── 自动分类 ────────────────────────────────────────────────────────

    async def _classify(self, file_name: str, text: str) -> str:
        # 优先 LLM（前 200 字）
        if self.llm and text and text.strip():
            try:
                tag = await self._classify_with_llm(file_name, text[:300])
                if tag in TAG_KEYWORDS:
                    return tag
            except Exception as e:
                logger.warning("classify_with_llm failed · fallback heuristic: %s", e)

        # 兜底：启发式
        return heuristic_tag(file_name, text)

    async def _classify_with_llm(self, file_name: str, sample: str) -> str:
        prompt = (
            f"判断这份资料的类别。文件名：{file_name}\n"
            f"内容前 300 字：{sample}\n\n"
            "只返回一个词（不要解释 · 不要标点）：产品 / 活动 / 反馈 / 培训 / 价格 / 其他"
        )
        raw = await self.llm.respond(
            prompt=prompt,
            tenant_id="_classifier_",
            model_route="deepseek_v32",
            max_tokens=10,
            system="你是文件分类器 · 严格只输出一个词",
        )
        tag = raw.strip().split()[0] if raw else ""
        for valid in TAG_KEYWORDS:
            if valid in tag:
                return valid
        return "其他"

    # ─── DB 持久化 ───────────────────────────────────────────────────────

    async def _save_record(self, record: ContentRecord) -> None:
        try:
            from server.models import ContentUpload
        except ImportError:
            logger.warning("ContentUpload ORM not registered · skip save")
            return
        async with session_scope() as session:
            session.add(
                ContentUpload(
                    file_id=record.file_id,
                    tenant_id=record.tenant_id,
                    file_name=record.file_name,
                    file_type=record.file_type,
                    size_bytes=record.size_bytes,
                    parsed_chunks=record.parsed_chunks,
                    source_tag=record.source_tag,
                    knowledge_chunk_ids=json.dumps(record.knowledge_chunk_ids),
                    marketing_plan_id=record.marketing_plan_id,
                    uploaded_at=record.uploaded_at,
                )
            )

    async def _update_marketing_id(self, file_id: str, plan_id: str) -> None:
        try:
            from server.models import ContentUpload
        except ImportError:
            return
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(ContentUpload).where(ContentUpload.file_id == file_id)
                )
            ).scalar_one_or_none()
            if row:
                row.marketing_plan_id = plan_id

    # ─── 查询 ────────────────────────────────────────────────────────────

    async def list_uploads(self, tenant_id: str, limit: int = 100) -> list[dict]:
        try:
            from server.models import ContentUpload
        except ImportError:
            return []
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(ContentUpload)
                    .where(ContentUpload.tenant_id == tenant_id)
                    .order_by(ContentUpload.uploaded_at.desc())
                    .limit(limit)
                )
            ).scalars().all()
            return [
                {
                    "file_id": r.file_id,
                    "file_name": r.file_name,
                    "file_type": r.file_type,
                    "size_bytes": r.size_bytes,
                    "parsed_chunks": r.parsed_chunks,
                    "source_tag": r.source_tag,
                    "marketing_plan_id": r.marketing_plan_id,
                    "uploaded_at": r.uploaded_at,
                }
                for r in rows
            ]

    async def delete(self, file_id: str) -> bool:
        try:
            from server.models import ContentUpload
        except ImportError:
            return False
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(ContentUpload).where(ContentUpload.file_id == file_id)
                )
            ).scalar_one_or_none()
            if not row:
                return False
            tenant_id = row.tenant_id
            file_name = row.file_name
            await session.delete(row)
        # 同时删 KB 中对应 source 的 chunks
        try:
            await self.kb.delete_source(tenant_id, file_name)
        except Exception as e:
            logger.warning("kb delete_source failed: %s", e)
        return True


# ─── 工具函数 ────────────────────────────────────────────────────────────

def _extract_docx(file_bytes: bytes) -> str:
    """python-docx 解析 · 没装库返回空字符串。"""
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except Exception as e:
        logger.warning("docx parse skipped (lib missing or bad file): %s", e)
        return ""
