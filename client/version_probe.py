"""版本探针 · 探测微信 PC 版本 · 加载对应控件路径配置。"""

from __future__ import annotations

import json
import logging
import platform
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DEFAULT_VERSION_RANGES: dict[str, str] = {
    "3.9": "v3_9.json",
    "4.0": "v4_0.json",
    "4.1": "v4_1.json",
}


def detect_wechat_version() -> Optional[str]:
    """Windows: 探测微信 PC 版本 (Weixin.exe 4.x / WeChat.exe 3.x)。
    macOS: 返回 None（mock）。"""
    if platform.system() != "Windows":
        return None

    try:
        import win32api  # type: ignore

        # 微信 4.x 国内版 = Weixin.exe (改名了); 老版 3.x = WeChat.exe
        candidates = [
            "C:\\Program Files\\Tencent\\Weixin\\Weixin.exe",
            "C:\\Program Files (x86)\\Tencent\\Weixin\\Weixin.exe",
            "C:\\Program Files\\Tencent\\WeChat\\WeChat.exe",
            "C:\\Program Files (x86)\\Tencent\\WeChat\\WeChat.exe",
        ]
        for path in candidates:
            if Path(path).exists():
                info = win32api.GetFileVersionInfo(path, "\\")
                ms = info["FileVersionMS"]
                ls = info["FileVersionLS"]
                v = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
                logger.info("detected WeChat version: %s @ %s", v, path)
                return v
        # 兜底: 找正在跑的进程
        try:
            import psutil  # type: ignore
            for proc in psutil.process_iter(['name', 'exe']):
                name = (proc.info.get('name') or '').lower()
                if name in ('weixin.exe', 'wechat.exe'):
                    exe = proc.info.get('exe')
                    if exe and Path(exe).exists():
                        info = win32api.GetFileVersionInfo(exe, "\\")
                        ms = info["FileVersionMS"]
                        ls = info["FileVersionLS"]
                        v = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
                        logger.info("detected WeChat version (via process): %s @ %s", v, exe)
                        return v
        except Exception as e:
            logger.warning("psutil probe failed: %s", e)
    except Exception as e:
        logger.warning("version probe failed: %s", e)

    return None


def load_ui_config(version: Optional[str], config_dir: Path) -> dict:
    """根据版本号选择对应 JSON 控件路径。"""
    if not version:
        logger.warning("no version detected, fallback to v4_0.json")
        cfg_file = "v4_0.json"
    else:
        major_minor = ".".join(version.split(".")[:2])
        cfg_file = DEFAULT_VERSION_RANGES.get(major_minor, "v4_0.json")

    path = config_dir / cfg_file
    if not path.exists():
        logger.error("UI config not found: %s", path)
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_major_minor(version: str) -> tuple[int, int]:
    """1.2.3.4 → (1, 2)。"""
    m = re.match(r"(\d+)\.(\d+)", version)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))
