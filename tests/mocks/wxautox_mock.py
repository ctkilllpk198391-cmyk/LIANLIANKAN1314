"""mock wxautox 接口 · macOS 上跑 client.watcher 用。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MockMessage:
    sender: str
    content: str
    timestamp: int = 0
    msg_type: str = "text"


class MockWeChat:
    """模拟 wxauto.WeChat 实例。"""

    def __init__(self):
        self._inbox: dict[str, list[MockMessage]] = {}

    def feed(self, chat_name: str, sender: str, content: str) -> None:
        """测试用：注入一条新消息。"""
        self._inbox.setdefault(chat_name, []).append(MockMessage(sender, content))

    def GetAllNewMessage(self) -> dict[str, list[MockMessage]]:
        snap = {k: list(v) for k, v in self._inbox.items()}
        self._inbox.clear()
        return snap

    def SendMsg(self, text: str, chat_id: str) -> bool:
        return True
