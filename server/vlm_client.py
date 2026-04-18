"""VLM 客户端 · 阿里云百炼 Qwen-VL · OpenAI 兼容协议 · mock fallback。

申请: https://bailian.console.aliyun.com/
Endpoint: https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions
Model: qwen-vl-max
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

from shared.errors import HermesUnreachableError

logger = logging.getLogger(__name__)

DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_MOCK_DESCRIPTION = "[图片描述：一张产品图 · mock 模式]"


class QwenVLClient:
    """阿里云百炼 qwen-vl-max API · OpenAI 兼容协议。"""

    name = "qwen_vl_max"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "qwen-vl-max",
        mock: Optional[bool] = None,
    ):
        self.api_key = api_key or os.getenv("BAIYANG_VLM_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
        self.model = model
        # mock=True 显式传入 | 无 api_key | 环境变量 BAIYANG_VLM_MOCK=true → mock 模式
        if mock is not None:
            self.mock = mock
        else:
            env_mock = os.getenv("BAIYANG_VLM_MOCK", "").lower() == "true"
            self.mock = env_mock or not self.api_key

    async def describe(self, image_url: str, prompt: Optional[str] = None) -> str:
        """看图 + 用户问题 → 文字描述。mock 模式返回伪描述。"""
        if not image_url:
            return ""

        if self.mock:
            if prompt:
                return f"[图片描述：一张产品图 · mock 模式] 用户问：{prompt}"
            return _MOCK_DESCRIPTION

        user_content = [
            {"type": "image_url", "image_url": {"url": image_url}},
        ]
        if prompt:
            user_content.append({"type": "text", "text": prompt})
        else:
            user_content.append({"type": "text", "text": "请描述这张图片的内容，重点识别产品名称、价格、数量、类型等关键信息。"})

        body = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 200,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{DASHSCOPE_BASE_URL}/chat/completions"

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(url, headers=headers, json=body) as r:
                if r.status >= 500:
                    raise HermesUnreachableError(f"qwen-vl 5xx: {r.status}")
                data = await r.json()
                return data["choices"][0]["message"]["content"]
