"""e2e fixture · 关 scheduler · 强制 mock · 复用 app_client。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))


@pytest_asyncio.fixture
async def e2e_client(monkeypatch) -> AsyncIterator:
    """端到端客户端 · 关 scheduler + 全 mock + 多 tenant。"""
    monkeypatch.setenv("BAIYANG_DISABLE_SCHEDULER", "true")
    monkeypatch.setenv("BAIYANG_HERMES_MOCK", "true")
    monkeypatch.setenv("BAIYANG_NOTIFIER_MOCK", "true")
    monkeypatch.setenv("BAIYANG_EMBEDDER_MOCK", "true")
    monkeypatch.setenv("BAIYANG_CLASSIFIER", "rule")  # 用 rule 模式 · 减少 LLM 依赖

    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    monkeypatch.setenv("BAIYANG_DB_URL", f"sqlite+aiosqlite:///{tmp_db.name}")

    tmp_yaml = tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8")
    yaml.safe_dump({
        "tenants": [
            {
                "tenant_id": "tenant_e2e",
                "boss_name": "连大哥",
                "plan": "pro",
                "daily_quota": 100,
                "style_hints": "直接简洁 · 适当卖萌",
            }
        ]
    }, tmp_yaml, allow_unicode=True)
    tmp_yaml.close()
    monkeypatch.setenv("BAIYANG_TENANTS_PATH", tmp_yaml.name)

    from server.db import reset_engine_for_tests
    await reset_engine_for_tests()

    from httpx import ASGITransport, AsyncClient
    from server.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client

    await reset_engine_for_tests()
    try:
        os.unlink(tmp_db.name)
    except OSError:
        pass
    try:
        os.unlink(tmp_yaml.name)
    except OSError:
        pass
