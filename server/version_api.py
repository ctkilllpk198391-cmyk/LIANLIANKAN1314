"""版本信息 API · F3 自动更新服务端。

GET /v1/version → 返回 latest_version + download_url + min_supported + notes
"""

from __future__ import annotations

LATEST_VERSION = "0.1.0"
DOWNLOAD_BASE = "https://download.wechat-agent.example/v"
MIN_SUPPORTED = "0.1.0"


def get_version_info() -> dict:
    """返回最新版本信息，供客户端自动更新使用。"""
    return {
        "latest_version": LATEST_VERSION,
        "download_url": f"{DOWNLOAD_BASE}{LATEST_VERSION}/WechatAgent-Setup.exe",
        "min_supported": MIN_SUPPORTED,
        "notes": "首版",
    }
