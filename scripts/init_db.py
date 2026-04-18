"""初始化 SQLite + 应用 schema。

用法：
  python scripts/init_db.py         # 默认 ./data/wechat_agent.db
  BAIYANG_DB_URL=postgresql://... python scripts/init_db.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.db import get_engine  # noqa: E402
from server.models import Base  # noqa: E402


async def _create_all() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ 所有 schema 已创建")


def main() -> None:
    asyncio.run(_create_all())


if __name__ == "__main__":
    main()
