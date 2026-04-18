"""FDW F2 · 客户端激活流程 · mock 友好。"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
from typing import Optional

logger = logging.getLogger("baiyang.client.activation")


def _get_machine_guid() -> Optional[str]:
    """读取 Windows Machine GUID。非 Windows 返 None（测试时可传 None 用 sha256 兜底）。"""
    if platform.system() != "Windows":
        return None
    try:
        import winreg  # type: ignore[import]
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
        )
        guid, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(guid)
    except Exception as e:
        logger.warning("failed to read MachineGuid: %s", e)
        return None


class ActivationFlow:
    """客户端激活流程。调用方负责 DPAPI 加密存盘 device_token。"""

    def __init__(self, http_session=None):
        """http_session: httpx.AsyncClient 或兼容对象 · None 时内部创建。"""
        self._session = http_session

    async def activate_with_code(
        self,
        code: str,
        server_url: str,
        machine_guid: Optional[str] = None,
    ) -> str:
        """POST /v1/activate · 返 device_token。

        machine_guid 为 None 时服务端用 sha256(code) 兜底。
        调用方负责 DPAPI 加密存盘。
        """
        if machine_guid is None:
            machine_guid = _get_machine_guid()

        payload: dict = {"code": code}
        if machine_guid:
            payload["machine_guid"] = machine_guid

        if self._session is not None:
            resp = await self._session.post(f"{server_url}/v1/activate", json=payload)
            resp.raise_for_status()
            data = resp.json()
        else:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.post(f"{server_url}/v1/activate", json=payload)
                resp.raise_for_status()
                data = resp.json()

        token = data.get("device_token")
        if not token:
            raise ValueError(f"server returned no device_token: {data}")

        logger.info("activated successfully, token=%s...", token[:8])
        return token

    async def send_heartbeat(self, device_token: str, server_url: str) -> bool:
        """POST /v1/activation/heartbeat · 返 True/False。"""
        headers = {"Authorization": f"Bearer {device_token}"}
        try:
            if self._session is not None:
                resp = await self._session.post(
                    f"{server_url}/v1/activation/heartbeat",
                    headers=headers,
                )
                return resp.status_code == 200
            else:
                import httpx
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        f"{server_url}/v1/activation/heartbeat",
                        headers=headers,
                    )
                    return resp.status_code == 200
        except Exception as e:
            logger.warning("heartbeat failed: %s", e)
            return False
