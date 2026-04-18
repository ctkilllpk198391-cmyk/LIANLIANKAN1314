"""F3 · CLI · 上传知识库 · 切 chunk + embedding + 写库。

用法：
    python -m scripts.ingest_knowledge --tenant tenant_0001 --source products.md --file ./products.md
    python -m scripts.ingest_knowledge --tenant tenant_0001 --source price_list.csv --file ./price.csv --tags 价格,促销
    python -m scripts.ingest_knowledge --tenant tenant_0001 --source products.md --delete

每次重复 ingest 同一 source 会先删旧再写新（幂等）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from server.knowledge_base import KnowledgeBase
from server.models import Base
from server.db import get_engine


async def _async_main(args) -> int:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    kb = KnowledgeBase()

    if args.delete:
        n = await kb.delete_source(args.tenant, args.source)
        print(f"[delete] tenant={args.tenant} source={args.source} removed_chunks={n}")
        return 0

    if not args.file or not Path(args.file).exists():
        print(f"[error] file not found: {args.file}", file=sys.stderr)
        return 2

    text = Path(args.file).read_text(encoding="utf-8")
    if not text.strip():
        print(f"[error] file empty: {args.file}", file=sys.stderr)
        return 3

    # 幂等 · 先删同 source
    deleted = await kb.delete_source(args.tenant, args.source)
    if deleted:
        print(f"[overwrite] removed {deleted} old chunks for source={args.source}")

    tags = [t.strip() for t in args.tags.split(",")] if args.tags else []
    n = await kb.ingest(args.tenant, args.source, text, tags=tags)
    print(f"[ok] tenant={args.tenant} source={args.source} chunks={n} tags={tags}")

    stats = await kb.stats(args.tenant)
    print(f"[stats] {stats}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="ingest knowledge base content for a tenant")
    p.add_argument("--tenant", required=True, help="tenant_id")
    p.add_argument("--source", required=True, help="source label (e.g. products.md)")
    p.add_argument("--file", help="file path to ingest")
    p.add_argument("--tags", default="", help="comma-separated tags")
    p.add_argument("--delete", action="store_true", help="delete all chunks of this source")
    args = p.parse_args()
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    sys.exit(main())
