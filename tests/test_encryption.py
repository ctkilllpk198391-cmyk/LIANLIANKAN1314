"""T4 · 数据护城河 · TenantKMS 单元测试 · ≥8 用例。"""

from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import pytest

from server.encryption import TenantKMS, get_default_kms, reset_default_kms


@pytest.fixture(autouse=True)
def reset_singleton():
    """每个测试前后重置单例 · 避免污染。"""
    reset_default_kms()
    yield
    reset_default_kms()


@pytest.fixture
def tmp_kms(tmp_path):
    """使用临时目录的 KMS 实例 · 测试隔离。"""
    return TenantKMS(backend="fernet", key_dir=str(tmp_path / "keys"))


# --------------------------------------------------------------------------- #
# 1. 同 tenant 第二次拿到同一个 key
# --------------------------------------------------------------------------- #
def test_get_or_create_key_persists(tmp_kms):
    key1 = tmp_kms.get_or_create_key("tenant_abc")
    key2 = tmp_kms.get_or_create_key("tenant_abc")
    assert key1 == key2, "同 tenant 两次获取的 key 必须相同"


# --------------------------------------------------------------------------- #
# 2. 不同 tenant 拿到不同 key
# --------------------------------------------------------------------------- #
def test_get_or_create_key_per_tenant_unique(tmp_kms):
    key_a = tmp_kms.get_or_create_key("tenant_a")
    key_b = tmp_kms.get_or_create_key("tenant_b")
    assert key_a != key_b, "不同 tenant 必须有独立 key"


# --------------------------------------------------------------------------- #
# 3. bytes 加解密轮转
# --------------------------------------------------------------------------- #
def test_encrypt_decrypt_round_trip(tmp_kms):
    plaintext = b"Hello, World! \xe4\xb8\xad\xe6\x96\x87"
    ciphertext = tmp_kms.encrypt("t1", plaintext)
    assert ciphertext != plaintext, "密文不能等于明文"
    recovered = tmp_kms.decrypt("t1", ciphertext)
    assert recovered == plaintext, "解密后必须还原原文"


# --------------------------------------------------------------------------- #
# 4. 用错误 tenant 解密必须失败
# --------------------------------------------------------------------------- #
def test_decrypt_with_wrong_tenant_fails(tmp_kms):
    from cryptography.fernet import InvalidToken

    ciphertext = tmp_kms.encrypt("tenant_owner", b"secret data")
    with pytest.raises((InvalidToken, Exception)):
        tmp_kms.decrypt("tenant_other", ciphertext)


# --------------------------------------------------------------------------- #
# 5. str 便捷方法
# --------------------------------------------------------------------------- #
def test_encrypt_str_decrypt_str(tmp_kms):
    original = "客户敏感信息：过敏原 = 花生"
    encrypted = tmp_kms.encrypt_str("t_str", original)
    assert isinstance(encrypted, str), "encrypt_str 应返回 str"
    assert encrypted != original, "加密后应与原文不同"
    recovered = tmp_kms.decrypt_str("t_str", encrypted)
    assert recovered == original, "decrypt_str 应还原原字符串"


# --------------------------------------------------------------------------- #
# 6. key 文件权限必须是 600
# --------------------------------------------------------------------------- #
def test_key_file_permissions(tmp_kms):
    tmp_kms.get_or_create_key("perm_tenant")
    key_dir = tmp_kms.key_dir
    key_file = key_dir / "perm_tenant.key"
    assert key_file.exists(), "key 文件应已创建"
    file_mode = stat.S_IMODE(os.stat(key_file).st_mode)
    assert file_mode == 0o600, f"key 文件权限应为 600，实际: {oct(file_mode)}"


# --------------------------------------------------------------------------- #
# 7. rotate 抛 NotImplementedError
# --------------------------------------------------------------------------- #
def test_rotate_raises_not_implemented(tmp_kms):
    with pytest.raises(NotImplementedError):
        tmp_kms.rotate("any_tenant")


# --------------------------------------------------------------------------- #
# 8. 模块级单例行为
# --------------------------------------------------------------------------- #
def test_default_singleton(tmp_path, monkeypatch):
    """get_default_kms() 两次调用返回同一对象。"""
    # 使用 monkeypatch 让单例使用临时目录
    monkeypatch.setenv("HOME", str(tmp_path))
    kms1 = get_default_kms()
    kms2 = get_default_kms()
    assert kms1 is kms2, "get_default_kms() 应返回同一个单例实例"


# --------------------------------------------------------------------------- #
# 9. 加密后密文可持久化（跨 KMS 实例读取）
# --------------------------------------------------------------------------- #
def test_ciphertext_persists_across_instances(tmp_path):
    """销毁 KMS 实例后新建实例仍能解密（key 从磁盘读取）。"""
    key_dir = str(tmp_path / "persist_keys")
    kms1 = TenantKMS(key_dir=key_dir)
    ciphertext = kms1.encrypt("t_persist", b"persistent secret")

    # 新建实例（内存 cache 清空）
    kms2 = TenantKMS(key_dir=key_dir)
    recovered = kms2.decrypt("t_persist", ciphertext)
    assert recovered == b"persistent secret"


# --------------------------------------------------------------------------- #
# 10. 加密空字节串
# --------------------------------------------------------------------------- #
def test_encrypt_empty_bytes(tmp_kms):
    ciphertext = tmp_kms.encrypt("t_empty", b"")
    recovered = tmp_kms.decrypt("t_empty", ciphertext)
    assert recovered == b""
