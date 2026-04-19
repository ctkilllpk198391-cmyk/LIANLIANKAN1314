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
        # MiniMax Anthropic 兼容 endpoint: /v1/messages(标准 Anthropic 路径)
        # M2.7-highspeed 强制输出 thinking 块 · thinking 吃 200-500 tokens · 若 max_tokens 不够
        # 则 text 块被切光 · 返空字串 · 客户端以为"没回". 预留 1000 tokens 给 thinking.
        effective_max = max(max_tokens + 1000, 1500)
        url = f"{self.base_url}/v1/messages"
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        body: dict = {
            "model": self.model,
            "max_tokens": effective_max,
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
                # M2.7-highspeed 响应: content = [{type:thinking,...}, {type:text,text:...}]
                # 只取 text 块 · thinking 是内部推理不能发客户
                content = data.get("content", [])
                if isinstance(content, list):
                    text = "".join(c.get("text", "") for c in content if c.get("type") == "text")
                    if text:
                        return text
                    # text 块为空 · 退化:stop_reason=max_tokens 说明 thinking 吃完了 · 不该发 thinking
                    stop_reason = data.get("stop_reason", "")
                    raise HermesUnreachableError(
                        f"minimax M2.7 returned empty text (stop_reason={stop_reason} · thinking overflow)"
                    )
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


class Route302Client(BaseLLMClient):
    """302.AI 聚合 API · 一 key 调 DeepSeek V4 / GLM-5.1 / 豆包 Seed-2 / Qwen3.6 等 100+ 模型。

    OpenAI 兼容协议 · Base URL: https://api.302.ai/v1
    申请: https://302.ai/ · 文档: https://doc-en.302.ai/
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: str = "deepseek-chat",
        name: Optional[str] = None,
        mock: bool = False,
    ):
        self.api_key = api_key or os.getenv("OPENAI_302_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_302_BASE_URL") or "https://api.302.ai/v1"
        self.model = model
        self.name = name or f"route302_{model.replace('-', '_').replace('.', '_')}"
        self.mock = mock or not self.api_key

    async def chat(
        self,
        prompt: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system: Optional[str] = None,
    ) -> str:
        if self.mock:
            return f"[mock·{self.name}] {prompt[:30]}... → 302 聚合回复"

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        url = f"{self.base_url}/chat/completions"
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
                    raise HermesUnreachableError(f"302.ai 5xx: {r.status}")
                if r.status >= 400:
                    err = await r.text()
                    raise HermesUnreachableError(f"302.ai {r.status}: {err[:200]}")
                data = await r.json()
                return data["choices"][0]["message"]["content"]


# 302.AI 路由的 model 常量（2026-04-18 锁定 · 连大哥 5 场景）
ROUTE_302_MODELS = {
    "deepseek_v4": "deepseek-chat",           # 高意向/大额客户 · 中文销售话术最强
    "deepseek_r1": "deepseek-reasoner",       # 推理/纠错/长文档
    "glm_51": "glm-4.5",                       # 情感/投诉/共情 · 中文共情第一
    "doubao_seed2": "doubao-seed-1-6-pro",    # 朋友圈图文 · 多媒体最强
    "qwen36_plus": "qwen-max-latest",          # 备用 · OCR/多模态
}


class LLMRegistry:
    """统一注册中心 · model_router 通过 name 获取 client。"""

    def __init__(self):
        self._clients: dict[str, BaseLLMClient] = {}
        self._aliases: dict[str, str] = {}

    def register(self, client: BaseLLMClient) -> None:
        self._clients[client.name] = client

    def register_alias(self, alias: str, target_name: str) -> None:
        """Wave 5 · 给已注册 client 加别名(M4 router v4 用)。"""
        self._aliases[alias] = target_name

    def get(self, name: str) -> BaseLLMClient:
        if name in self._clients:
            return self._clients[name]
        if name in self._aliases:
            return self._clients[self._aliases[name]]
        raise KeyError(f"LLM client '{name}' not registered")

    def has(self, name: str) -> bool:
        return name in self._clients or name in self._aliases

    def list_available(self) -> list[str]:
        return list(self._clients.keys()) + list(self._aliases.keys())


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

    # 302.AI 聚合 · 注册 5 个 variant(连大哥 5 场景锁定)
    if mock or os.getenv("OPENAI_302_API_KEY"):
        for alias, model_id in ROUTE_302_MODELS.items():
            reg.register(Route302Client(model=model_id, name=f"route302_{alias}", mock=mock))

    reg.register(LocalVLLMClient(mock=True))

    # Wave 5 M4 · MiniMax M2.7 Token Plan 别名(router v4 返回这个名字)
    if reg.has("minimax_m25_lightning"):
        reg.register_alias("minimax_m27_tokenplan", "minimax_m25_lightning")
    return reg


def list_available_routes(registry: LLMRegistry) -> list[str]:
    return registry.list_available()
