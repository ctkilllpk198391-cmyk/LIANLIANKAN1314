"""客户端自动更新模块 · F3。

启动时调 server /v1/version 比对版本号，有新版本则静默下载，
下次启动时通过 boot script 替换可执行文件。
"""

from __future__ import annotations

import logging
import os
import platform
import stat
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("baiyang.updater")


def _version_tuple(v: str) -> tuple[int, ...]:
    """把 '1.2.3' 拆成 (1, 2, 3)，比较用。"""
    try:
        return tuple(int(x) for x in v.strip().split("."))
    except ValueError:
        return (0,)


@dataclass
class UpdateInfo:
    latest_version: str
    download_url: str
    min_supported: str
    notes: str = ""


class Updater:
    """自动更新器。

    Args:
        current_version: 当前客户端版本（如 '0.1.0'）。
        server_url: server 根 URL（如 'http://127.0.0.1:8327'）。
        api_client: 可选外部注入的 aiohttp session / httpx.AsyncClient；
                    为 None 时内部懒创建 httpx.AsyncClient。
    """

    def __init__(
        self,
        current_version: str,
        server_url: str,
        api_client=None,
    ):
        self.current_version = current_version
        self.server_url = server_url.rstrip("/")
        self._api_client = api_client

    async def _get(self, url: str) -> dict:
        """通用 GET，返回 JSON dict。支持外部注入的 client（方便测试 mock）。"""
        if self._api_client is not None:
            # 兼容 httpx.AsyncClient 和 unittest mock
            if hasattr(self._api_client, "get"):
                resp = await self._api_client.get(url)
                if hasattr(resp, "json"):
                    data = resp.json()
                    return data() if callable(data) else data
                return {}
            return {}

        # 无注入 client · 用 httpx（可选依赖）
        try:
            import httpx  # noqa: PLC0415
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return resp.json()
        except Exception as exc:
            logger.warning("更新检查失败: %s", exc)
            return {}

    async def check(self) -> Optional[UpdateInfo]:
        """向 server /v1/version 查询最新版本信息。

        Returns:
            UpdateInfo（如果有新版本可用），否则 None。
        """
        url = f"{self.server_url}/v1/version"
        logger.debug("检查更新: GET %s", url)
        try:
            data = await self._get(url)
        except Exception as exc:
            logger.warning("更新检查网络异常: %s", exc)
            return None

        if not data:
            return None

        latest = data.get("latest_version", "")
        if not latest:
            return None

        if _version_tuple(latest) > _version_tuple(self.current_version):
            logger.info(
                "发现新版本 %s（当前 %s）",
                latest,
                self.current_version,
            )
            return UpdateInfo(
                latest_version=latest,
                download_url=data.get("download_url", ""),
                min_supported=data.get("min_supported", "0.0.0"),
                notes=data.get("notes", ""),
            )

        logger.debug("当前已是最新版本 %s", self.current_version)
        return None

    async def download(self, info: UpdateInfo, dest_dir: str) -> str:
        """将新版安装包异步下载到 dest_dir，返回本地文件路径。"""
        dest_path = Path(dest_dir) / f"WechatAgent-Setup-{info.latest_version}.exe"
        logger.info("下载新版本 %s → %s", info.download_url, dest_path)

        if self._api_client is not None:
            # 测试环境 · mock client
            if hasattr(self._api_client, "get"):
                resp = await self._api_client.get(info.download_url)
                content = getattr(resp, "content", b"mock_binary")
                if callable(content):
                    content = content()
                dest_path.write_bytes(content if isinstance(content, bytes) else b"mock_binary")
                return str(dest_path)

        try:
            import httpx  # noqa: PLC0415
            async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
                async with client.stream("GET", info.download_url) as resp:
                    resp.raise_for_status()
                    with open(dest_path, "wb") as f:
                        async for chunk in resp.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
        except Exception as exc:
            logger.error("下载失败: %s", exc)
            raise

        logger.info("下载完成: %s", dest_path)
        return str(dest_path)

    def schedule_apply_on_boot(self, downloaded_path: str) -> str:
        """写入 boot script，下次启动时自动替换可执行文件。

        Returns:
            写入的 script 文件路径。
        """
        exe_path = str(Path(downloaded_path).resolve())

        if platform.system() == "Windows":
            script_path = Path(tempfile.gettempdir()) / "wechat_agent_update.cmd"
            script_content = (
                "@echo off\r\n"
                "timeout /t 3 /nobreak >nul\r\n"
                f'copy /Y "{exe_path}" "%~dp0wechat_agent.exe"\r\n'
                f'start "" "%~dp0wechat_agent.exe"\r\n'
                'del "%~f0"\r\n'
            )
            script_path.write_text(script_content, encoding="gbk")
        else:
            # macOS / Linux（开发/测试用）
            script_path = Path(tempfile.gettempdir()) / "wechat_agent_update.sh"
            script_content = (
                "#!/usr/bin/env bash\n"
                "sleep 3\n"
                f'cp -f "{exe_path}" "$(dirname "$0")/wechat_agent"\n'
                f'"$(dirname "$0")/wechat_agent" &\n'
                'rm -- "$0"\n'
            )
            script_path.write_text(script_content)
            script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)

        logger.info("已写入 boot script: %s", script_path)
        return str(script_path)
