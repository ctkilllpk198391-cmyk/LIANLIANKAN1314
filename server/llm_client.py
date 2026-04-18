"""LLMClient · 统一 LLM 调用入口（直连 API · 走 llm_clients registry）。

# 历史命名说明
此文件原名 `hermes_bridge.py` · 类原名 `HermesBridge`。
"hermes" 是无关项目（whale_tracker）的命名遗留 · 与本项目 wechat_agent 无关。
新代码请直接 `from server.llm_client import LLMClient`。
旧代码可继续 `from server.hermes_bridge import HermesBridge`（向后兼容 alias · 等所有旧测试迁移完后删除）。

# 设计
- 通过 model_route 字符串选择具体 client
- 路由降级：preferred 不可用 → 按拟人优先级 fallback (minimax/doubao/deepseek/glm)
- system 由 caller (generator/prompt_builder) 构建后传入 · 防 prompt 散落
- 失败兜底：所有 client 挂掉 → 用 mock minimax 兜底返回（避免阻塞链路）
"""

from __future__ import annotations

import logging
from typing import Optional

from server.llm_clients import LLMRegistry, build_default_registry
from shared.errors import HermesUnreachableError

logger = logging.getLogger(__name__)


class LLMClient:
    """统一 LLM 调用入口 · 通过 model_route 选择具体 client。"""

    def __init__(
        self,
        base_url: Optional[str] = None,  # 兼容老接口 · 不再使用
        mock: bool = True,
        timeout_sec: int = 30,
        registry: Optional[LLMRegistry] = None,
    ):
        self.mock = mock
        self.registry = registry or build_default_registry(mock=mock)

    async def respond(
        self,
        prompt: str,
        tenant_id: str,
        model_route: str,
        max_tokens: int = 300,
        style_hints: Optional[str] = None,  # 老接口兼容 · 不再使用
        system: Optional[str] = None,        # 由 generator/prompt_builder 构建后传入
    ) -> str:
        # 兼容老 model_route 别名
        route_alias = {
            "hermes_default": "doubao_15pro",
            "claude_sonnet": "glm_51",
            "lora:auto": "local_vllm",
        }
        if model_route in route_alias:
            model_route = route_alias[model_route]
        if model_route.startswith("lora:"):
            model_route = "local_vllm"

        # 路由降级：preferred 不可用 → 按拟人优先级 fallback
        if not self.registry.has(model_route):
            for fallback in ("minimax_m25_lightning", "doubao_15pro", "deepseek_v32", "glm_51"):
                if self.registry.has(fallback):
                    logger.info("route %s 不可用 · 降级到 %s", model_route, fallback)
                    model_route = fallback
                    break
            else:
                raise HermesUnreachableError("无可用 LLM client · 请配置至少 1 个 API key")

        client = self.registry.get(model_route)
        # system 由 caller 构建（防散落） · 这里只兜底一个最简版
        fallback_system = (
            f"你是 {style_hints[:30] if style_hints else '老板'} 的微信回复助手。"
            "约束：≤200 字 · 自然口语 · 不绝对承诺。"
        )

        try:
            return await client.chat(
                prompt=prompt,
                max_tokens=max_tokens,
                system=system or fallback_system,
            )
        except Exception as e:
            logger.warning("%s 失败 · fallback mock: %s", model_route, e)
            from server.llm_clients import MiniMaxClient
            return await MiniMaxClient(mock=True).chat(prompt, max_tokens, system=system)

    async def health(self) -> bool:
        return len(self.registry.list_available()) > 0
