"""Wave 14 · 素材库 · tenant 级图片管理.

目录结构:
    tenants/{tenant_id}/media/
        index.json          # { "filename": {alt_text, tags, category, uploaded_at} }
        <filename>.jpg      # 图片原文件

接口:
    - list_images(tenant_id) → List[MediaItem]  给 prompt_builder 列表
    - pick_by_filename(tenant_id, filename) → Path | None  AI 用 [[IMG:xxx]] 引用后实际拿文件
    - register(tenant_id, filename, alt_text, tags, category) → bool  后台上传时调

AI 怎么用:
    prompt_builder 列出"可用图片: product_01.jpg(红色连衣裙) / product_02.jpg(黑色半裙)"
    AI 回复内嵌 "[[IMG:product_01.jpg]] 这款您看下"
    _dispatch_reply 正则解析 [[IMG:xxx]] → 先 SendImage · 后 SendText(剩余文字)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MEDIA_ROOT = Path("tenants")
IMG_TAG_PATTERN = re.compile(r"\[\[IMG:([^\]\[]+?)\]\]")


@dataclass
class MediaItem:
    filename: str
    alt_text: str
    tags: list[str]
    category: str
    uploaded_at: int
    full_path: Path


def _tenant_media_dir(tenant_id: str) -> Path:
    return MEDIA_ROOT / tenant_id / "media"


def _index_path(tenant_id: str) -> Path:
    return _tenant_media_dir(tenant_id) / "index.json"


def _load_index(tenant_id: str) -> dict:
    p = _index_path(tenant_id)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("media index corrupt for %s: %s", tenant_id, e)
        return {}


def _save_index(tenant_id: str, index: dict) -> None:
    d = _tenant_media_dir(tenant_id)
    d.mkdir(parents=True, exist_ok=True)
    _index_path(tenant_id).write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def list_images(tenant_id: str, limit: int = 20) -> list[MediaItem]:
    """列 tenant 所有素材 · 默认上限 20."""
    index = _load_index(tenant_id)
    items: list[MediaItem] = []
    base = _tenant_media_dir(tenant_id)
    for filename, meta in index.items():
        full = base / filename
        if not full.exists():
            continue
        items.append(MediaItem(
            filename=filename,
            alt_text=meta.get("alt_text", ""),
            tags=meta.get("tags", []),
            category=meta.get("category", "general"),
            uploaded_at=meta.get("uploaded_at", 0),
            full_path=full,
        ))
    items.sort(key=lambda x: x.uploaded_at, reverse=True)
    return items[:limit]


def pick_by_filename(tenant_id: str, filename: str) -> Optional[Path]:
    """AI 用 [[IMG:xxx]] 引用 · 这里拿具体文件路径。防目录穿越."""
    # 禁止 .. · / · 绝对路径
    if ".." in filename or "/" in filename or filename.startswith(".") or not filename:
        return None
    p = _tenant_media_dir(tenant_id) / filename
    return p if p.exists() else None


def register(
    tenant_id: str,
    filename: str,
    alt_text: str = "",
    tags: Optional[list[str]] = None,
    category: str = "general",
) -> bool:
    """登记一张已在目录里的图到 index.json. 后台上传时调."""
    full = _tenant_media_dir(tenant_id) / filename
    if not full.exists():
        logger.warning("media register: file not exist %s", full)
        return False
    index = _load_index(tenant_id)
    index[filename] = {
        "alt_text": alt_text,
        "tags": tags or [],
        "category": category,
        "uploaded_at": int(time.time()),
    }
    _save_index(tenant_id, index)
    return True


def render_prompt_block(tenant_id: str, limit: int = 10) -> str:
    """Wave 14 · 给 prompt_builder 用 · 列可用图片供 AI 引用."""
    items = list_images(tenant_id, limit=limit)
    if not items:
        return ""
    lines = ["\n# 可用图片（AI 可引用 · 用 `[[IMG:filename]]` 内嵌）"]
    for it in items:
        desc = it.alt_text or it.category
        tag_str = " · ".join(it.tags[:3]) if it.tags else ""
        parts = [it.filename, desc]
        if tag_str:
            parts.append(tag_str)
        lines.append(f"- {' | '.join(parts)}")
    lines.append("（引用示例：`[[IMG:{}]]`）".format(items[0].filename))
    return "\n".join(lines)


def extract_image_refs(text: str) -> tuple[str, list[str]]:
    """从 AI 回复中解析 [[IMG:xxx]] 标记 · 返(去标记后文字, filename 列表)."""
    filenames: list[str] = []

    def _collect(m):
        filenames.append(m.group(1).strip())
        return ""

    clean = IMG_TAG_PATTERN.sub(_collect, text).strip()
    return clean, filenames
