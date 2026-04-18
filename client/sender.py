"""HumanLikeSender · HumanCursor + wxautox 模拟人手发送。"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Optional

from shared.proto import SendAck

logger = logging.getLogger(__name__)


class HumanLikeSender:
    def __init__(self, mock: bool = False):
        self.mock = mock
        self._wx = None
        self._cursor = None

    def _ensure_runtime(self) -> None:
        if self.mock:
            return
        if self._wx is None:
            WeChat = None
            try:
                from wxautox import WeChat  # type: ignore
            except ImportError:
                from wxauto import WeChat  # type: ignore
            self._wx = WeChat()
        if self._cursor is None:
            try:
                from humancursor import SystemCursor  # type: ignore

                self._cursor = SystemCursor()
            except ImportError:
                logger.warning("HumanCursor 未装 · 退化为直接 SendMsg")
                self._cursor = False  # 占位避免重复尝试

    async def send(self, chat_id: str, text: str) -> SendAck:
        msg_id = f"out_{int(time.time() * 1000)}"

        if self.mock:
            await asyncio.sleep(self._human_delay())
            logger.info("[MOCK send] chat=%s text=%s", chat_id, text[:30])
            return SendAck(msg_id=msg_id, sent_at=int(time.time()), success=True)

        try:
            self._ensure_runtime()
            await asyncio.sleep(self._human_delay())

            if self._cursor and self._cursor is not False:
                # 鼠标走人类轨迹（窗口位置由 wxauto 提供）
                pass  # Phase 3 实现：定位输入框坐标 → cursor.move_to(...)

            await asyncio.get_event_loop().run_in_executor(
                None, self._wx.SendMsg, text, chat_id
            )
            return SendAck(msg_id=msg_id, sent_at=int(time.time()), success=True)
        except Exception as e:
            logger.exception("send failed: %s", e)
            return SendAck(msg_id=msg_id, sent_at=int(time.time()), success=False, error=str(e))

    @staticmethod
    def _human_delay() -> float:
        """模拟人类思考 + 输入时间。"""
        return random.uniform(1.5, 4.0)
