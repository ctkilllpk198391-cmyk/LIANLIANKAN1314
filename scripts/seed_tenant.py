"""种子 tenant_0001 = 连大哥 · 0 号客户。"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.tenant import TenantManager  # noqa: E402
from shared.proto import TenantConfig  # noqa: E402


async def _seed() -> None:
    tm = TenantManager()
    tc = TenantConfig(
        tenant_id="tenant_0001",
        boss_name="连大哥",
        plan="pro",
        daily_quota=100,
        style_hints="直接、简洁、轻微幽默；避免过度客套；不堆 emoji",
    )
    await tm.upsert_to_db(tc)
    print(f"✅ 种子 tenant 写入：{tc.tenant_id} ({tc.boss_name})")


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
