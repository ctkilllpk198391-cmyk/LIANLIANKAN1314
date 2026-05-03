"""GeWe API engine — V12 替代 wxpadpro_bridge.

真 API: http://api.geweapi.com/gewe/v2/api/<endpoint>
真 Header: X-GEWE-TOKEN: <token>
真 Body 必填: appId (微信节点 ID)
"""

from __future__ import annotations

import logging
import os

import aiohttp

logger = logging.getLogger(__name__)

GEWE_BASE = os.environ.get("GEWE_BASE", "http://api.geweapi.com/gewe/v2/api")


class GeweEngine:
    def __init__(self, token: str | None = None, app_id: str | None = None):
        self.token = token or os.environ.get("GEWE_TOKEN", "")
        self.app_id = app_id or os.environ.get("GEWE_APP_ID", "")
        self._session: aiohttp.ClientSession | None = None

    async def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-GEWE-TOKEN": self.token, "Content-Type": "application/json"}
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _post(self, path: str, body: dict) -> dict:
        body = {"appId": self.app_id, **body}
        s = await self._http()
        url = f"{GEWE_BASE}/{path.lstrip('/')}"
        async with s.post(url, json=body) as resp:
            data = await resp.json()
            if data.get("ret") != 200:
                logger.warning("GeWe %s fail: %s", path, data)
            return data

    # ─── 消息 ────────────────────────────────
    async def send_text(self, to_wxid: str, content: str) -> dict:
        return await self._post("message/postText", {"toWxid": to_wxid, "content": content})

    async def send_image(self, to_wxid: str, image_url: str) -> dict:
        return await self._post("message/postImage", {"toWxid": to_wxid, "imgUrl": image_url})

    async def send_file(self, to_wxid: str, file_url: str, file_name: str) -> dict:
        return await self._post(
            "message/postFile",
            {"toWxid": to_wxid, "fileUrl": file_url, "fileName": file_name},
        )

    async def revoke(self, to_wxid: str, msg_id: str, new_msg_id: str, create_time: int) -> dict:
        return await self._post(
            "message/revokeMsg",
            {"toWxid": to_wxid, "msgId": msg_id, "newMsgId": new_msg_id, "createTime": create_time},
        )

    # ─── 联系人 / 群 ───────────────────────────
    async def get_contacts(self) -> dict:
        return await self._post("contacts/fetchContactsList", {})

    async def get_contact_info(self, wxid: str) -> dict:
        return await self._post("contacts/getDetailInfo", {"wxids": [wxid]})

    # ─── 账号 / 节点 ───────────────────────────
    async def check_online(self) -> dict:
        return await self._post("login/checkOnline", {})

    async def get_profile(self) -> dict:
        return await self._post("personal/getProfile", {})

    # ─── 回调配置 ───────────────────────────
    async def set_callback(self, callback_url: str) -> dict:
        return await self._post("tools/setCallback", {"callbackUrl": callback_url, "token": self.token})
