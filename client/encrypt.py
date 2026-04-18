"""加密占位 · Phase 1 stub · Phase 4 真正实现 DPAPI + WSS/mTLS。"""

from __future__ import annotations

import logging
import platform

logger = logging.getLogger(__name__)


def encrypt_token(plaintext: str) -> str:
    """Phase 1 stub. Phase 4: Windows DPAPI · macOS Keychain · Linux Secret Service."""
    if platform.system() == "Windows":
        try:
            import win32crypt  # type: ignore

            ct = win32crypt.CryptProtectData(plaintext.encode("utf-8"), None, None, None, None, 0)
            import base64

            return base64.b64encode(ct).decode("ascii")
        except ImportError:
            logger.warning("win32crypt 未装 · 明文存（仅 dev）")
    return f"PLAINTEXT::{plaintext}"


def decrypt_token(ciphertext: str) -> str:
    """Phase 1 stub。"""
    if ciphertext.startswith("PLAINTEXT::"):
        return ciphertext.removeprefix("PLAINTEXT::")
    if platform.system() == "Windows":
        try:
            import base64

            import win32crypt  # type: ignore

            raw = base64.b64decode(ciphertext.encode("ascii"))
            _, plaintext = win32crypt.CryptUnprotectData(raw, None, None, None, 0)
            return plaintext.decode("utf-8")
        except ImportError:
            return ""
    return ""
