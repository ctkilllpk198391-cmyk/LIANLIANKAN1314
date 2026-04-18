"""DoubaoASRClient 单元测试 · 全 mock · ≥4 用例。"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio

from server.asr_client import DoubaoASRClient, MOCK_RESULT


# ── 用例 1：显式 mock=True 返回固定字符串 ───────────────────────────────────
@pytest.mark.asyncio
async def test_explicit_mock_flag():
    """mock=True 时，任何 voice_url 都返回 MOCK_RESULT。"""
    client = DoubaoASRClient(mock=True)
    result = await client.transcribe("https://example.com/audio.mp3")
    assert result == MOCK_RESULT
    assert isinstance(result, str)
    assert len(result) > 0


# ── 用例 2：无 API key 自动走 mock ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_api_key_uses_mock(monkeypatch):
    """没有 DOUBAO_ASR_API_KEY 时，自动 mock。"""
    monkeypatch.delenv("DOUBAO_ASR_API_KEY", raising=False)
    monkeypatch.delenv("DOUBAO_ASR_APP_ID", raising=False)
    monkeypatch.delenv("BAIYANG_ASR_MOCK", raising=False)

    client = DoubaoASRClient(api_key=None, app_id=None)
    assert client.mock is True

    result = await client.transcribe("https://example.com/voice.mp3")
    assert result == MOCK_RESULT


# ── 用例 3：mock transcribe 返回字符串 ────────────────────────────────────
@pytest.mark.asyncio
async def test_mock_transcribe_returns_string():
    """mock 模式返回非空字符串且类型正确。"""
    client = DoubaoASRClient(mock=True)
    result = await client.transcribe("https://cdn.example.com/chat/voice_001.mp3")
    assert isinstance(result, str)
    assert result  # 非空


# ── 用例 4：空 voice_url 返回空字符串 ────────────────────────────────────────
@pytest.mark.asyncio
async def test_transcribe_empty_voice_url_returns_empty():
    """voice_url 为空或纯空白时返回空字符串，不调用 API。"""
    client = DoubaoASRClient(mock=True)

    assert await client.transcribe("") == ""
    assert await client.transcribe("   ") == ""
    assert await client.transcribe(None) == ""  # type: ignore[arg-type]


# ── 用例 5：env BAIYANG_ASR_MOCK=true 强制 mock ───────────────────────────
@pytest.mark.asyncio
async def test_env_mock_flag(monkeypatch):
    """BAIYANG_ASR_MOCK=true 时，即使传了 api_key 也走 mock。"""
    monkeypatch.setenv("BAIYANG_ASR_MOCK", "true")
    # 传入假 key，但 env 强制 mock
    client = DoubaoASRClient(api_key="fake-key", app_id="fake-app-id")
    assert client.mock is True
    result = await client.transcribe("https://example.com/test.mp3")
    assert result == MOCK_RESULT


# ── 用例 6：mock 模式不同 URL 都返回相同固定文字 ─────────────────────────────
@pytest.mark.asyncio
async def test_mock_consistent_result():
    """mock 模式对任意 URL 返回相同结果（幂等）。"""
    client = DoubaoASRClient(mock=True)
    r1 = await client.transcribe("https://cdn.example.com/a.mp3")
    r2 = await client.transcribe("https://cdn.example.com/b.mp3")
    r3 = await client.transcribe("https://cdn.example.com/c.wav")
    assert r1 == r2 == r3 == MOCK_RESULT


# ── 用例 7：lang 参数不影响 mock 结果 ────────────────────────────────────────
@pytest.mark.asyncio
async def test_mock_lang_param_ignored():
    """mock 模式下 lang 参数不影响返回值。"""
    client = DoubaoASRClient(mock=True)
    zh_result = await client.transcribe("https://example.com/audio.mp3", lang="zh")
    en_result = await client.transcribe("https://example.com/audio.mp3", lang="en")
    assert zh_result == en_result == MOCK_RESULT
