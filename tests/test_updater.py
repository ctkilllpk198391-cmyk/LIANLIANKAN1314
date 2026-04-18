"""tests/test_updater.py · F3 自动更新单元测试 · ≥4 用例。"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from client.updater import UpdateInfo, Updater, _version_tuple


# ─── 辅助 ─────────────────────────────────────────────────────────────────────

def _make_api_client(data: dict):
    """构建返回固定 JSON 的 mock api_client。"""
    resp = MagicMock()
    resp.json = MagicMock(return_value=data)
    resp.content = b"fake_exe_content"
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    return client


# ─── _version_tuple ───────────────────────────────────────────────────────────

def test_version_tuple_basic():
    assert _version_tuple("1.2.3") == (1, 2, 3)


def test_version_tuple_single():
    assert _version_tuple("2") == (2,)


def test_version_tuple_invalid():
    assert _version_tuple("bad") == (0,)


# ─── check() ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_returns_update_info_when_newer():
    """server 返回更新版本 → check 返回 UpdateInfo。"""
    client = _make_api_client({
        "latest_version": "0.2.0",
        "download_url": "https://example.com/WechatAgent-Setup.exe",
        "min_supported": "0.1.0",
        "notes": "测试更新",
    })
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327", api_client=client)
    info = await updater.check()
    assert info is not None
    assert info.latest_version == "0.2.0"
    assert info.download_url == "https://example.com/WechatAgent-Setup.exe"
    assert info.notes == "测试更新"


@pytest.mark.asyncio
async def test_check_returns_none_when_same_version():
    """server 版本与当前相同 → check 返回 None。"""
    client = _make_api_client({
        "latest_version": "0.1.0",
        "download_url": "https://example.com/x.exe",
        "min_supported": "0.1.0",
        "notes": "",
    })
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327", api_client=client)
    info = await updater.check()
    assert info is None


@pytest.mark.asyncio
async def test_check_returns_none_when_older():
    """server 版本低于当前（回退场景）→ check 返回 None。"""
    client = _make_api_client({
        "latest_version": "0.0.9",
        "download_url": "https://example.com/x.exe",
        "min_supported": "0.0.9",
        "notes": "",
    })
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327", api_client=client)
    info = await updater.check()
    assert info is None


@pytest.mark.asyncio
async def test_check_returns_none_on_empty_response():
    """server 返回空数据 → check 不崩溃，返回 None。"""
    client = _make_api_client({})
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327", api_client=client)
    info = await updater.check()
    assert info is None


@pytest.mark.asyncio
async def test_check_handles_network_error():
    """网络异常 → check 不崩溃，返回 None。"""
    client = MagicMock()
    client.get = AsyncMock(side_effect=Exception("连接拒绝"))
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327", api_client=client)
    info = await updater.check()
    assert info is None


# ─── download() ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_download_writes_file():
    """download 把内容写到 dest_dir 并返回正确路径。"""
    client = _make_api_client({})
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327", api_client=client)

    info = UpdateInfo(
        latest_version="0.2.0",
        download_url="https://example.com/WechatAgent-Setup-0.2.0.exe",
        min_supported="0.1.0",
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        path = await updater.download(info, tmpdir)
        assert Path(path).exists()
        assert "0.2.0" in path


# ─── schedule_apply_on_boot() ─────────────────────────────────────────────────

def test_schedule_apply_on_boot_creates_script():
    """schedule_apply_on_boot 写入 boot script 文件。"""
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327")
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        exe_path = f.name

    try:
        script_path = updater.schedule_apply_on_boot(exe_path)
        assert Path(script_path).exists()
        content = Path(script_path).read_text(encoding="utf-8", errors="replace")
        assert exe_path in content
    finally:
        Path(exe_path).unlink(missing_ok=True)
        Path(script_path).unlink(missing_ok=True)


def test_schedule_apply_on_boot_returns_string():
    """schedule_apply_on_boot 返回值是字符串路径。"""
    updater = Updater(current_version="0.1.0", server_url="http://127.0.0.1:8327")
    with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
        exe_path = f.name
    try:
        result = updater.schedule_apply_on_boot(exe_path)
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        Path(exe_path).unlink(missing_ok=True)
        path = Path(result)
        if path.exists():
            path.unlink(missing_ok=True)


# ─── UpdateInfo dataclass ─────────────────────────────────────────────────────

def test_update_info_defaults():
    info = UpdateInfo(
        latest_version="1.0.0",
        download_url="https://example.com/x.exe",
        min_supported="0.9.0",
    )
    assert info.notes == ""


def test_update_info_with_notes():
    info = UpdateInfo(
        latest_version="1.0.0",
        download_url="https://example.com/x.exe",
        min_supported="0.9.0",
        notes="重大更新",
    )
    assert info.notes == "重大更新"
