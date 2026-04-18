"""数据库 · SQLAlchemy async engine + session。"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DEFAULT_DB_URL = "sqlite+aiosqlite:///./data/wechat_agent.db"


def get_db_url() -> str:
    return os.getenv("BAIYANG_DB_URL", DEFAULT_DB_URL)


def _ensure_sqlite_dir(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    db_path = url.split(":///")[-1]
    if db_path == ":memory:" or not db_path:
        return
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)


_engine = None
_session_factory = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        url = get_db_url()
        _ensure_sqlite_dir(url)
        _engine = create_async_engine(url, echo=False, future=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_session_factory():
    if _session_factory is None:
        get_engine()
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def reset_engine_for_tests() -> None:
    """测试用 · 重置 engine 以使用新 URL。"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
