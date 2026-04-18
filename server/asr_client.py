"""豆包 ASR 客户端 · 火山引擎语音识别 · 默认中文 · mock fallback。

申请：https://console.volcengine.com/speech/
Endpoint: https://openspeech.bytedance.com/api/v1/vc
Model: bigmodel

环境变量：
  DOUBAO_ASR_APP_ID   火山引擎语音识别 App ID
  DOUBAO_ASR_API_KEY  火山引擎语音识别 API Key
  BAIYANG_ASR_MOCK    设为 "true" 强制 mock 模式
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

ASR_ENDPOINT = "https://openspeech.bytedance.com/api/v1/vc"
ASR_MODEL = "bigmodel"
MOCK_RESULT = "[语音转文字 mock]"


class DoubaoASRClient:
    """火山引擎语音识别 · 豆包系列 · 默认中文。

    没有 API key 或 BAIYANG_ASR_MOCK=true 时自动走 mock。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        app_id: Optional[str] = None,
        mock: Optional[bool] = None,
    ):
        self.api_key = api_key or os.getenv("DOUBAO_ASR_API_KEY")
        self.app_id = app_id or os.getenv("DOUBAO_ASR_APP_ID")

        env_mock = os.getenv("BAIYANG_ASR_MOCK", "").lower() == "true"
        if mock is not None:
            self.mock = mock
        else:
            self.mock = env_mock or not self.api_key or not self.app_id

    async def transcribe(self, voice_url: str, lang: str = "zh") -> str:
        """音频 URL → 文字。mock 返 "[语音转文字 mock]"。

        Args:
            voice_url: 可公网访问的音频文件 URL（mp3/wav/m4a 等）
            lang: 语言代码，默认中文 "zh"

        Returns:
            识别文字；空 URL 返回空字符串；mock 返回固定字符串。
        """
        if not voice_url or not voice_url.strip():
            return ""

        if self.mock:
            logger.debug("asr mock: voice_url=%s", voice_url)
            return MOCK_RESULT

        return await self._call_api(voice_url, lang)

    async def _call_api(self, voice_url: str, lang: str) -> str:
        """调用火山引擎 ASR API。"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "app": {
                "appid": self.app_id,
                "cluster": "volc.bigasr.sauc.duration",
            },
            "user": {"uid": "wechat_agent"},
            "audio": {
                "format": "mp3",
                "url": voice_url,
                "lang": lang,
            },
            "request": {
                "model_name": ASR_MODEL,
                "enable_punc": True,
            },
        }
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
            async with s.post(ASR_ENDPOINT, headers=headers, json=body) as r:
                if r.status >= 500:
                    logger.error("asr 5xx: %d", r.status)
                    return MOCK_RESULT
                if r.status >= 400:
                    err = await r.text()
                    logger.error("asr 4xx: %d %s", r.status, err[:200])
                    return MOCK_RESULT
                data = await r.json()
                # 火山引擎 ASR 响应格式
                utterances = data.get("result", {}).get("utterances", [])
                if utterances:
                    return "".join(u.get("text", "") for u in utterances)
                # 兼容 text 直接返回
                return data.get("result", {}).get("text", MOCK_RESULT)
