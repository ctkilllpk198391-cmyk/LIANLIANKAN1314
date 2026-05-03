"""WeChatPadPro REST API engine — V11 替代 wxauto4.

真链 WeChatPadPro Docker (port 8080), 经 chisel 反向通道走客户机 IP 出口.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class WeChatPadProEngine:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        admin_key: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.admin_key = admin_key or os.environ.get("WECHATPAD_ADMIN_KEY", "")
        self.token = token  # 扫码登录后填
        self._session: Optional[aiohttp.ClientSession] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_login_qr(self, app_id: str = "") -> dict:
        """获取扫码登录二维码 URL. app_id 首登传空, 后续传上次返回值."""
        s = await self._ensure_session()
        url = f"{self.base_url}/admin/GetLoginQrCode"
        async with s.post(
            url,
            params={"key": self.admin_key},
            json={"appId": app_id, "proxy": ""},
        ) as resp:
            data = await resp.json()
            logger.info("GetLoginQrCode: %s", data)
            return data

    async def check_login(self, uuid: str) -> dict:
        """轮询扫码是否完成. 完成后返回 token + appId."""
        s = await self._ensure_session()
        url = f"{self.base_url}/admin/CheckLoginQrCode"
        async with s.post(
            url,
            params={"key": self.admin_key},
            json={"uuid": uuid},
        ) as resp:
            return await resp.json()

    async def send_text(self, to_user: str, content: str) -> dict:
        """发文本消息."""
        s = await self._ensure_session()
        url = f"{self.base_url}/message/SendTextMessage"
        async with s.post(
            url,
            params={"key": self.token},
            json={"toWxid": to_user, "content": content},
        ) as resp:
            data = await resp.json()
            if data.get("Code") != 200:
                logger.error("send_text fail: %s", data)
            return data

    async def send_image(self, to_user: str, image_url: str) -> dict:
        s = await self._ensure_session()
        url = f"{self.base_url}/message/SendImageMessage"
        async with s.post(
            url,
            params={"key": self.token},
            json={"toWxid": to_user, "imageUrl": image_url},
        ) as resp:
            return await resp.json()

    async def get_contacts(self) -> list:
        s = await self._ensure_session()
        url = f"{self.base_url}/friend/GetContactList"
        async with s.post(
            url,
            params={"key": self.token},
            json={},
        ) as resp:
            data = await resp.json()
            return data.get("Data", {}).get("ContactList", [])

    async def set_callback(self, callback_url: str) -> dict:
        """注册消息推送回调. WeChatPadPro 收到新消息会 POST callback_url."""
        s = await self._ensure_session()
        url = f"{self.base_url}/admin/SetMessageCallback"
        async with s.post(
            url,
            params={"key": self.admin_key},
            json={"callbackUrl": callback_url},
        ) as resp:
            return await resp.json()
