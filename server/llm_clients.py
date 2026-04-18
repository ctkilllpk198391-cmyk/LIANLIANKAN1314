"""LLM 客户端 · DeepSeek V3.2 + GLM-5.1 + Claude（保留）· 统一接口。

成本经济学（2026-04）:
- DeepSeek V3.2:  $0.28 / $0.42 per MTok · 90% 场景 · ¥0.0013/条
- GLM-5.1:        $0.95 / $3.15 per MTok · 高风险 10% · ¥0.0057/条
- Claude Sonnet:  $3.00 / $15.0 per MTok · 国际客户备份 · ¥0.03/条

千客户月成本 ~¥6K（vs 自部署 A100 ¥10K · 平衡点 1700 客户）。
"""

from __future__ import annotations

import logging
import os
from typing import Literal, Optional

import aiohttp

from shared.errors import HermesUnreachableError

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
ANTHROPIC_BASE_URL = "https://api.anthropic.com/v1"
DOUBAO_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
# MiniMax 国内站（连大哥用的 Token Plan 极速版）vs 国际站
MINIMAX_DOMESTIC_BASE = "https://api.minimaxi.com"     # sk-cp- Token Plan
MINIMAX_INTERNATIONAL_BASE = "https://api.minimax.io"  # 标准 pay-as-you-go


class BaseLLMClient:
    name: str = "base"

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        raise NotImplementedError


class DeepSeekClient(BaseLLMClient):
    """DeepSeek V3.2 · 性价比王 · 90% 场景默认。"""

    name = "deepseek_v32"

    def __init__(self, api_key: Optional[str] = None, model: str = "deepseek-chat", mock: bool = False):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.model = model
        self.mock = mock or not self.api_key

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        if self.mock:
            return f"[mock·{self.name}] {prompt[:30]}... → 您好，稍等我看看哈～"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        url = f"{DEEPSEEK_BASE_URL}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"deepseek 5xx: {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"]


class GLMClient(BaseLLMClient):
    """GLM-5.1 · 中文当前第一（BenchLM 84）· 高风险场景。"""

    name = "glm_51"

    def __init__(self, api_key: Optional[str] = None, model: str = "glm-5.1", mock: bool = False):
        self.api_key = api_key or os.getenv("ZHIPU_API_KEY")
        self.model = model
        self.mock = mock or not self.api_key

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        if self.mock:
            return f"[mock·{self.name}] {prompt[:30]}... → 您好，这边帮您看一下，请稍候。"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        url = f"{ZHIPU_BASE_URL}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"glm 5xx: {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"]


class ClaudeClient(BaseLLMClient):
    """Claude Sonnet 4.6 · 国际客户备份 · 暂时保留。"""

    name = "claude_sonnet_46"

    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-4-6", mock: bool = False):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self.mock = mock or not self.api_key

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        if self.mock:
            return f"[mock·{self.name}] {prompt[:30]}... → 您好"

        url = f"{ANTHROPIC_BASE_URL}/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "system": system or "",
            "messages": [{"role": "user", "content": prompt}],
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"claude 5xx: {r.status}")
                data = await r.json()
                return data["content"][0]["text"]


class DoubaoClient(BaseLLMClient):
    """豆包 1.5 Pro · 字节 · 拟人化最强 · 中文用户实测自然度第一。

    走火山引擎 ark API · 兼容 OpenAI 协议。
    申请：https://console.volcengine.com/ark
    """

    name = "doubao_15pro"

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint_id: Optional[str] = None,
        model: str = "doubao-1-5-pro-32k",
        mock: bool = False,
    ):
        self.api_key = api_key or os.getenv("DOUBAO_API_KEY")
        self.endpoint_id = endpoint_id or os.getenv("DOUBAO_ENDPOINT_ID") or model
        self.model = self.endpoint_id
        self.mock = mock or not self.api_key

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        if self.mock:
            return f"[mock·{self.name}] {prompt[:30]}... → 嗨亲~ 我看下哈，稍等几分钟就给您答复～😊"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        url = f"{DOUBAO_BASE_URL}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"doubao 5xx: {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"]


class MiniMaxClient(BaseLLMClient):
    """MiniMax · 自动适配两种 API key 类型。

    sk-cp-* (Token Plan 国内极速版 · 连大哥版本):
      - Base: https://api.minimaxi.com/anthropic
      - 协议: Anthropic 兼容（x-api-key header）
      - Endpoint: /messages
      - 默认模型: MiniMax-M2.7-highspeed（100 TPS · 当前 SOTA）
      - 包月制：Plus ¥98/月 · Ultra ¥899/月

    其他 (国际站 PAYG):
      - Base: https://api.minimax.io/v1
      - 协议: OpenAI 兼容 chatcompletion_v2
      - 按量计费 $0.30/$2.40 per MTok
    """

    name = "minimax_m25_lightning"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        mock: bool = False,
    ):
        self.api_key = api_key or os.getenv("MINIMAX_API_KEY")
        self.mock = mock or not self.api_key

        self.is_token_plan = bool(self.api_key and self.api_key.startswith("sk-cp-"))
        if self.is_token_plan:
            self.base_url = base_url or f"{MINIMAX_DOMESTIC_BASE}/anthropic"
            self.model = model or "MiniMax-M2.7-highspeed"
        else:
            self.base_url = base_url or f"{MINIMAX_INTERNATIONAL_BASE}/v1"
            self.model = model or "MiniMax-M2.5-Lightning"

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        if self.mock:
            kind = "TokenPlan" if self.is_token_plan else "PAYG"
            return f"[mock·{self.name}·{kind}] {prompt[:30]}... → 哎呀这个我懂啦~ 您稍等下我马上给您答复哈！"

        if self.is_token_plan:
            return await self._chat_anthropic(prompt, max_tokens, temperature, system)
        return await self._chat_openai(prompt, max_tokens, temperature, system)

    async def _chat_anthropic(self, prompt, max_tokens, temperature, system):
        # MiniMax Anthropic 兼容 endpoint: /v1/messages（标准 Anthropic 路径）
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"minimax token-plan 5xx: {r.status}")
                if r.status >= 400:
                    err = await r.text()
                    raise HermesUnreachableError(f"minimax {r.status}: {err[:200]}")
                data = await r.json()
                # M2.7-highspeed 响应可能含 thinking 块 + text 块 · 只取 text
                content = data.get("content", [])
                if isinstance(content, list):
                    return "".join(c.get("text", "") for c in content if c.get("type") == "text")
                return ""

    async def _chat_openai(self, prompt, max_tokens, temperature, system):
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        url = f"{self.base_url}/text/chatcompletion_v2"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"minimax payg 5xx: {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"]


class LocalVLLMClient(BaseLLMClient):
    """自部署 vLLM · Phase 7+ 接 client·LoRA"""

    name = "local_vllm"

    def __init__(self, base_url: str = "http://localhost:8000/v1", lora_id: Optional[str] = None, mock: bool = False):
        self.base_url = base_url.rstrip("/")
        self.lora_id = lora_id
        self.mock = mock

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        if self.mock:
            return f"[mock·{self.name}·{self.lora_id}] {prompt[:30]}... → 这是您的专属 AI 回复"

        url = f"{self.base_url}/completions"
        body = {
            "model": self.lora_id or "default",
            "prompt": (system + "\n\n" if system else "") + prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"vllm 5xx: {r.status}")
                data = await r.json()
                return data["choices"][0]["text"]


class LLMRegistry:
    """统一注册中心 · model_router 通过 name 获取 client。"""

    def __init__(self):
        self._clients: dict[str, BaseLLMClient] = {}

    def register(self, client: BaseLLMClient) -> None:
        self._clients[client.name] = client

    def get(self, name: str) -> BaseLLMClient:
        if name not in self._clients:
            raise KeyError(f"LLM client '{name}' not registered")
        return self._clients[name]

    def has(self, name: str) -> bool:
        return name in self._clients

    def list_available(self) -> list[str]:
        return list(self._clients.keys())


def build_default_registry(mock: bool = False) -> LLMRegistry:
    """奥卡姆剃刀：mock 模式全注册（测试需要） · real 模式只注册有 key 的。

    第一性原理：用户没买的 API key 不该假装存在 · 路由会自动降级。
    """
    reg = LLMRegistry()
    candidates = [
        (DoubaoClient, "DOUBAO_API_KEY"),
        (MiniMaxClient, "MINIMAX_API_KEY"),
        (DeepSeekClient, "DEEPSEEK_API_KEY"),
        (GLMClient, "ZHIPU_API_KEY"),
        (ClaudeClient, "ANTHROPIC_API_KEY"),
    ]
    for klass, env_var in candidates:
        if mock or os.getenv(env_var):
            reg.register(klass(mock=mock))
    reg.register(LocalVLLMClient(mock=True))
    return reg


def list_available_routes(registry: LLMRegistry) -> list[str]:
    return registry.list_available()
