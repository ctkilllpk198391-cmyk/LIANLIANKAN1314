"""VLM 客户端测试 · 全 mock 模式 · 不调真 API。"""

from __future__ import annotations

import os

import pytest

from server.vlm_client import QwenVLClient, _MOCK_DESCRIPTION


# ──────────────────────────────────────────────────────────────────────────────
# test_mock_describe_returns_string
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mock_describe_returns_string():
    """mock=True 时 describe 返回非空字符串。"""
    client = QwenVLClient(mock=True)
    result = await client.describe("https://example.com/product.jpg")
    assert isinstance(result, str)
    assert len(result) > 0


# ──────────────────────────────────────────────────────────────────────────────
# test_no_api_key_uses_mock
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_no_api_key_uses_mock(monkeypatch):
    """没有 api_key 且无环境变量时，自动进入 mock 模式返回伪描述。"""
    monkeypatch.delenv("BAIYANG_VLM_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("BAIYANG_VLM_MOCK", raising=False)

    client = QwenVLClient()  # 无 key → mock 自动生效
    assert client.mock is True

    result = await client.describe("https://example.com/img.png")
    assert result == _MOCK_DESCRIPTION


# ──────────────────────────────────────────────────────────────────────────────
# test_describe_with_prompt
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_describe_with_prompt():
    """mock 模式传入 prompt 时，返回值包含 prompt 内容。"""
    client = QwenVLClient(mock=True)
    user_prompt = "这个多少钱"
    result = await client.describe("https://example.com/product.jpg", prompt=user_prompt)
    assert isinstance(result, str)
    assert user_prompt in result


# ──────────────────────────────────────────────────────────────────────────────
# test_describe_empty_image_url
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_describe_empty_image_url():
    """image_url 为空字符串时，返回空字符串（不报错）。"""
    client = QwenVLClient(mock=True)
    result = await client.describe("")
    assert result == ""


# ──────────────────────────────────────────────────────────────────────────────
# test_explicit_mock_flag
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_explicit_mock_flag():
    """mock=True 显式传入时，即使设置了 API key 也走 mock 路径。"""
    client = QwenVLClient(api_key="fake-key-should-not-be-used", mock=True)
    assert client.mock is True
    result = await client.describe("https://example.com/product.jpg")
    assert _MOCK_DESCRIPTION in result


# ──────────────────────────────────────────────────────────────────────────────
# test_env_mock_flag
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_env_mock_flag(monkeypatch):
    """BAIYANG_VLM_MOCK=true 环境变量触发 mock，即使有 api_key。"""
    monkeypatch.setenv("BAIYANG_VLM_MOCK", "true")
    monkeypatch.setenv("BAIYANG_VLM_API_KEY", "any-key")

    client = QwenVLClient()
    assert client.mock is True

    result = await client.describe("https://example.com/product.jpg")
    assert isinstance(result, str)
    assert len(result) > 0


# ──────────────────────────────────────────────────────────────────────────────
# test_mock_no_prompt_returns_default_description
# ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_mock_no_prompt_returns_default_description():
    """mock 模式不传 prompt 时，返回标准伪描述字符串。"""
    client = QwenVLClient(mock=True)
    result = await client.describe("https://example.com/img.jpg")
    assert result == _MOCK_DESCRIPTION


# ──────────────────────────────────────────────────────────────────────────────
# test_client_name
# ──────────────────────────────────────────────────────────────────────────────
def test_client_name():
    """client.name 为 qwen_vl_max。"""
    client = QwenVLClient(mock=True)
    assert client.name == "qwen_vl_max"
