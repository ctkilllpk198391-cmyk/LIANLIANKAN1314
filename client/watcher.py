"""WeChatWatcher · 监听微信新消息 · 真模式 wxautox · mock 模式 macOS 跑通。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from client.api_client import ServerAPIClient
from shared.proto import InboundMsg, Suggestion

logger = logging.getLogger(__name__)


OnSuggestionCallback = Callable[[Suggestion], Awaitable[None]]


class WeChatWatcher:
    def __init__(
        self,
        server_url: str,
        tenant_id: str,
        mock: bool = False,
        on_suggestion: Optional[OnSuggestionCallback] = None,
    ):
        self.tenant_id = tenant_id
        self.mock = mock
        self.api = ServerAPIClient(server_url)
        self.on_suggestion = on_suggestion
        self._wx = None  # 真模式才注入
        self._running = False

    def _ensure_wx(self) -> None:
        if self.mock:
            return
        if self._wx is None:
            # 多引擎 fallback (按微信版本优先级):
            # wxautox4 = 商业 Plus 版 for 微信 4.0+(最新)
            # wxauto4 = 开源 for 微信 4.0
            # wxautox = 商业 Plus 版 for 微信 3.x
            # wxauto = 开源 for 微信 3.x
            engines = [
                ('wxautox4', '商业 Plus · 微信 4.x'),
                ('wxauto4',  '开源 · 微信 4.x'),
                ('wxautox',  '商业 Plus · 微信 3.x'),
                ('wxauto',   '开源 · 微信 3.x'),
            ]
            last_err = None
            for mod_name, desc in engines:
                try:
                    mod = __import__(mod_name)
                    WeChatCls = getattr(mod, 'WeChat', None)
                    if WeChatCls is None:
                        logger.warning("引擎 %s 没有 WeChat 类,跳过", mod_name)
                        continue
                    logger.info("尝试引擎: %s (%s)", mod_name, desc)
                    self._wx = WeChatCls()
                    self._engine_name = mod_name
                    logger.info("✅ 微信自动化引擎激活: %s", mod_name)
                    return
                except ImportError as e:
                    logger.info("引擎 %s 未安装: %s", mod_name, e)
                    last_err = e
                except Exception as e:
                    logger.warning("引擎 %s 初始化失败: %s", mod_name, e)
                    last_err = e
            raise RuntimeError(
                "所有微信自动化引擎都不可用。已尝试: " +
                ", ".join(m for m, _ in engines) +
                f" · 最后错误: {last_err}"
            )

    async def start(self) -> None:
        self._ensure_wx()
        self._running = True
        if self.mock:
            logger.info("mock 模式启动 · 不实际监听微信")
            return

        loop = asyncio.get_event_loop()
        while self._running:
            try:
                msgs = await loop.run_in_executor(None, self._wx.GetAllNewMessage)
                for chat_name, message_list in (msgs or {}).items():
                    for m in message_list:
                        await self._handle_raw(chat_name, m)
            except Exception as e:
                logger.exception("watcher loop error: %s", e)
            await asyncio.sleep(1.0)

    def stop(self) -> None:
        self._running = False

    async def _handle_raw(self, chat_name: str, raw_msg) -> None:
        # raw_msg 结构来自 wxauto · 字段名以 wxauto 4.x 为准
        # 这里抽象为 InboundMsg
        text = getattr(raw_msg, "content", "") or str(raw_msg)
        sender = getattr(raw_msg, "sender", chat_name)
        if not text.strip():
            return

        msg = InboundMsg(
            tenant_id=self.tenant_id,
            chat_id=chat_name,
            sender_id=sender,
            sender_name=sender,
            text=text,
            timestamp=int(time.time()),
        )
        await self.submit(msg)

    async def submit(self, msg: InboundMsg) -> Suggestion:
        suggestion = await self.api.submit_inbound(msg)
        if self.on_suggestion:
            await self.on_suggestion(suggestion)
        return suggestion
