"""pytest fixtures · 临时 SQLite + tenants.yaml + mock hermes。"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def temp_db(monkeypatch) -> AsyncIterator[str]:
    """每个测试一个临时 SQLite。"""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite+aiosqlite:///{tmp.name}"
    monkeypatch.setenv("BAIYANG_DB_URL", db_url)

    from server.db import reset_engine_for_tests

    await reset_engine_for_tests()

    from server.db import get_engine
    from server.models import Base
    from server import subscription as _sub  # noqa: F401  注册 Subscription 表

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield db_url

    await reset_engine_for_tests()
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


@pytest_asyncio.fixture
async def temp_tenants_yaml(tmp_path) -> Path:
    """临时 tenants.yaml，含 tenant_0001 + tenant_0002。"""
    path = tmp_path / "tenants.yaml"
    payload = {
        "tenants": [
            {
                "tenant_id": "tenant_0001",
                "boss_name": "连大哥",
                "plan": "pro",
                "daily_quota": 100,
                "style_hints": "直接简洁",
            },
            {
                "tenant_id": "tenant_0002",
                "boss_name": "测试客户B",
                "plan": "trial",
                "daily_quota": 30,
                "style_hints": "礼貌专业",
            },
        ]
    }
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


@pytest_asyncio.fixture
async def loaded_tenants(temp_db, temp_tenants_yaml):
    from server.tenant import TenantManager

    tm = TenantManager(config_path=temp_tenants_yaml)
    tm.load_from_yaml()
    for tc in tm.list_all():
        await tm.upsert_to_db(tc)
    return tm


@pytest_asyncio.fixture
async def app_client(temp_db, temp_tenants_yaml, monkeypatch):
    """提供 httpx AsyncClient · ASGI 直连 FastAPI app（不开端口）。"""
    monkeypatch.setenv("BAIYANG_TENANTS_PATH", str(temp_tenants_yaml))
    monkeypatch.setenv("BAIYANG_HERMES_MOCK", "true")
    monkeypatch.setenv("BAIYANG_CLASSIFIER", "rule")

    from httpx import ASGITransport, AsyncClient

    from server.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client
