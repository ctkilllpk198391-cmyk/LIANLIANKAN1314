"""LLM clients 测试 · 全 mock 模式 · 验证接口正确。"""

from __future__ import annotations

import pytest

from server.llm_clients import (
    ClaudeClient,
    DeepSeekClient,
    GLMClient,
    LLMRegistry,
    LocalVLLMClient,
    build_default_registry,
)


@pytest.mark.asyncio
async def test_deepseek_mock_returns_text():
    c = DeepSeekClient(mock=True)
    out = await c.chat("客户问 多少钱")
    assert "deepseek_v32" in out
    assert isinstance(out, str)


@pytest.mark.asyncio
async def test_glm_mock_returns_text():
    c = GLMClient(mock=True)
    out = await c.chat("投诉")
    assert "glm_51" in out


@pytest.mark.asyncio
async def test_claude_mock_returns_text():
    c = ClaudeClient(mock=True)
    out = await c.chat("hello")
    assert "claude_sonnet_46" in out


@pytest.mark.asyncio
async def test_local_vllm_mock_with_lora():
    c = LocalVLLMClient(lora_id="tenant_0001", mock=True)
    out = await c.chat("您好")
    assert "tenant_0001" in out


def test_registry_register_and_get():
    reg = LLMRegistry()
    reg.register(DeepSeekClient(mock=True))
    assert reg.has("deepseek_v32")
    c = reg.get("deepseek_v32")
    assert c.name == "deepseek_v32"


def test_registry_get_unknown_raises():
    reg = LLMRegistry()
    with pytest.raises(KeyError):
        reg.get("nonexistent")


def test_default_registry_has_6_clients():
    reg = build_default_registry(mock=True)
    names = reg.list_available()
    assert "doubao_15pro" in names
    assert "minimax_m25_lightning" in names  # v3.1: 升级到 M2.5-Lightning
    assert "deepseek_v32" in names
    assert "glm_51" in names
    assert "claude_sonnet_46" in names
    assert "local_vllm" in names


@pytest.mark.asyncio
async def test_doubao_mock():
    from server.llm_clients import DoubaoClient
    c = DoubaoClient(mock=True)
    out = await c.chat("您好")
    assert "doubao_15pro" in out


@pytest.mark.asyncio
async def test_minimax_payg_mock():
    """无 sk-cp- 前缀的 key 走 PAYG OpenAI 协议。"""
    from server.llm_clients import MiniMaxClient
    c = MiniMaxClient(api_key="some-payg-key", mock=True)
    assert c.is_token_plan is False
    assert c.model == "MiniMax-M2.5-Lightning"
    assert "minimax.io/v1" in c.base_url
    out = await c.chat("聊聊")
    assert "PAYG" in out


@pytest.mark.asyncio
async def test_minimax_token_plan_mock():
    """sk-cp- 前缀的 key 自动走 Token Plan Anthropic 协议（连大哥的极速版）。"""
    from server.llm_clients import MiniMaxClient
    c = MiniMaxClient(api_key="sk-cp-fake-test-key", mock=True)
    assert c.is_token_plan is True
    assert c.model == "MiniMax-M2.7-highspeed"  # 极速版默认
    assert "minimaxi.com/anthropic" in c.base_url
    out = await c.chat("聊聊")
    assert "TokenPlan" in out


def test_minimax_no_groupid_required():
    """v3.1: M2.5 的 v2 endpoint 不再需要 GroupId（旧 abab 才需要）。"""
    from server.llm_clients import MiniMaxClient
    c = MiniMaxClient(api_key="test", mock=False)
    # 不应抛 attribute error · 不应有 group_id 属性
    assert not hasattr(c, "group_id")


@pytest.mark.asyncio
async def test_no_api_key_auto_falls_to_mock():
    """没传 api_key 也没 env 变量 → 自动 mock 模式。"""
    import os
    saved = os.environ.pop("DEEPSEEK_API_KEY", None)
    try:
        c = DeepSeekClient()
        assert c.mock is True
        out = await c.chat("test")
        assert "mock" in out
    finally:
        if saved:
            os.environ["DEEPSEEK_API_KEY"] = saved


@pytest.mark.asyncio
async def test_hermes_bridge_routes_through_registry():
    from server.hermes_bridge import HermesBridge

    bridge = HermesBridge(mock=True)
    out = await bridge.respond(
        prompt="客户问砍价",
        tenant_id="tenant_0001",
        model_route="deepseek_v32",
    )
    assert isinstance(out, str)
    assert len(out) > 0


@pytest.mark.asyncio
async def test_hermes_bridge_legacy_alias():
    """v3: 老 model_route 名应自动 alias 到新 client。"""
    from server.hermes_bridge import HermesBridge

    bridge = HermesBridge(mock=True)
    out1 = await bridge.respond("test", "t", "hermes_default")
    out2 = await bridge.respond("test", "t", "claude_sonnet")
    out3 = await bridge.respond("test", "t", "lora:tenant_0001")
    assert "doubao_15pro" in out1   # v3: hermes_default → doubao（拟人冠军）
    assert "glm_51" in out2          # claude_sonnet → glm_51
    assert "local_vllm" in out3      # lora:* → local_vllm


@pytest.mark.asyncio
async def test_hermes_bridge_unknown_route_falls_back():
    """v4 简化：fallback 顺序 minimax → doubao → deepseek → glm。"""
    from server.hermes_bridge import HermesBridge

    bridge = HermesBridge(mock=True)
    out = await bridge.respond("test", "t", "unknown_model_xyz")
    assert any(x in out for x in ["minimax_m25_lightning", "doubao_15pro", "deepseek_v32"])


def test_model_router_greeting_picks_doubao():
    """v3: 拟人优先 · greeting → Doubao。"""
    from server.model_router import ModelRouter
    from shared.proto import IntentResult
    from shared.types import IntentEnum, RiskEnum

    r = ModelRouter()
    out = r.route("tenant_0001", IntentResult(intent=IntentEnum.GREETING, confidence=0.8, risk=RiskEnum.LOW))
    assert out == "doubao_15pro"


def test_model_router_inquiry_picks_deepseek():
    """v3: 询价走 deepseek（推理 + 便宜）。"""
    from server.model_router import ModelRouter
    from shared.proto import IntentResult
    from shared.types import IntentEnum, RiskEnum

    r = ModelRouter()
    out = r.route("tenant_0001", IntentResult(intent=IntentEnum.INQUIRY, confidence=0.8, risk=RiskEnum.LOW))
    assert out == "deepseek_v32"


def test_model_router_negotiation_picks_doubao():
    """v3: 砍价需要共情 · 走 doubao。"""
    from server.model_router import ModelRouter
    from shared.proto import IntentResult
    from shared.types import IntentEnum, RiskEnum

    r = ModelRouter()
    out = r.route("tenant_0001", IntentResult(intent=IntentEnum.NEGOTIATION, confidence=0.8, risk=RiskEnum.MEDIUM))
    assert out == "doubao_15pro"


def test_model_router_high_risk_picks_glm():
    from server.model_router import ModelRouter
    from shared.proto import IntentResult
    from shared.types import IntentEnum, RiskEnum

    r = ModelRouter()
    out = r.route("tenant_0001", IntentResult(intent=IntentEnum.COMPLAINT, confidence=0.9, risk=RiskEnum.HIGH))
    assert out == "glm_51"


def test_model_router_lora_ready_picks_vllm():
    from server.model_router import ModelRouter
    from shared.proto import IntentResult
    from shared.types import IntentEnum, RiskEnum

    r = ModelRouter()
    r.mark_lora_ready("tenant_0001")
    out = r.route("tenant_0001", IntentResult(intent=IntentEnum.GREETING, confidence=0.8, risk=RiskEnum.LOW))
    assert out == "local_vllm"
