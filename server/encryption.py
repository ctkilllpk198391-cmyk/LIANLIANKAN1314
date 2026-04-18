"""T4 · 数据护城河 · per-tenant 加密 + KMS 抽象层。

dev  = cryptography Fernet（本地 · 无网络依赖）
prod = AWS KMS / 阿里云 KMS（Phase 4 接入 · 现留接口）

key 存放：~/.wechat_agent_keys/{tenant_id}.key（chmod 600）
目录权限：chmod 700
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# 懒加载 cryptography · 未安装时给出清晰报错
# --------------------------------------------------------------------------- #
try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover
    Fernet = None  # type: ignore[assignment,misc]
    InvalidToken = Exception  # type: ignore[assignment,misc]


class TenantKMS:
    """per-tenant 加密 · 抽象层（dev=fernet · prod=AWS/阿里云 KMS）。"""

    def __init__(self, backend: str = "fernet", key_dir: Optional[str] = None):
        """
        key_dir 默认 ~/.wechat_agent_keys/ · 自动创建 · chmod 700
        """
        if Fernet is None:
            raise ImportError("cryptography 未安装 · 请执行: pip install cryptography>=42.0")

        self.backend = backend
        self.key_dir = Path(key_dir or "~/.wechat_agent_keys").expanduser()
        self.key_dir.mkdir(parents=True, exist_ok=True)
        # 目录权限 700（rwx------）
        self.key_dir.chmod(stat.S_IRWXU)
        self._cache: dict[str, Fernet] = {}

    # ------------------------------------------------------------------ #
    # Key 管理
    # ------------------------------------------------------------------ #

    def get_or_create_key(self, tenant_id: str) -> bytes:
        """每 tenant 一个 fernet key · 文件名 {tenant_id}.key · chmod 600。"""
        key_path = self.key_dir / f"{tenant_id}.key"

        if key_path.exists():
            raw = key_path.read_bytes().strip()
            return raw

        # 生成新 key
        raw = Fernet.generate_key()
        key_path.write_bytes(raw)
        # 权限 600（rw-------）
        key_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        logger.info("TenantKMS: 新建 key 文件 %s", key_path)
        return raw

    def _get_fernet(self, tenant_id: str) -> Fernet:
        if tenant_id not in self._cache:
            raw = self.get_or_create_key(tenant_id)
            self._cache[tenant_id] = Fernet(raw)
        return self._cache[tenant_id]

    # ------------------------------------------------------------------ #
    # 加解密（bytes）
    # ------------------------------------------------------------------ #

    def encrypt(self, tenant_id: str, plaintext: bytes | str) -> bytes:
        """返回 fernet token（base64 编码 · 安全）。"""
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        return self._get_fernet(tenant_id).encrypt(plaintext)

    def decrypt(self, tenant_id: str, ciphertext: bytes) -> bytes:
        """fernet 解密。"""
        return self._get_fernet(tenant_id).decrypt(ciphertext)

    # ------------------------------------------------------------------ #
    # 便捷方法（str ↔ str）
    # ------------------------------------------------------------------ #

    def encrypt_str(self, tenant_id: str, text: str) -> str:
        """便捷方法 · 返回 str（base64 ascii）。"""
        token: bytes = self.encrypt(tenant_id, text.encode("utf-8"))
        return token.decode("ascii")

    def decrypt_str(self, tenant_id: str, ciphertext: str) -> str:
        """便捷方法 · str → str。"""
        raw: bytes = self.decrypt(tenant_id, ciphertext.encode("ascii"))
        return raw.decode("utf-8")

    # ------------------------------------------------------------------ #
    # Key 轮换（prod 用 · 现留接口）
    # ------------------------------------------------------------------ #

    def rotate(self, tenant_id: str) -> None:
        """key 轮换 · prod 用 · 现在留接口。"""
        raise NotImplementedError("Key rotation is reserved for prod KMS integration (Phase 4)")


# --------------------------------------------------------------------------- #
# 模块级单例
# --------------------------------------------------------------------------- #

_default_kms: Optional[TenantKMS] = None


def get_default_kms() -> TenantKMS:
    """返回进程级默认 KMS 单例（懒初始化）。"""
    global _default_kms
    if _default_kms is None:
        _default_kms = TenantKMS()
    return _default_kms


def reset_default_kms() -> None:
    """重置单例（测试隔离用）。"""
    global _default_kms
    _default_kms = None
