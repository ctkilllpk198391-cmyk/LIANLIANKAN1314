"""跨 tenant 隔离强制测试。"""

from __future__ import annotations

import pytest

from server.tenant import TenantManager
from shared.errors import CrossTenantError, TenantNotFoundError


def test_enforce_isolation_passes_when_match():
    TenantManager.enforce_isolation("tenant_0001", "tenant_0001")  # 不抛


def test_enforce_isolation_raises_on_mismatch():
    with pytest.raises(CrossTenantError):
        TenantManager.enforce_isolation("tenant_0001", "tenant_0002")


def test_get_unknown_tenant_raises():
    tm = TenantManager()
    with pytest.raises(TenantNotFoundError):
        tm.get("tenant_999")


@pytest.mark.asyncio
async def test_load_from_yaml(temp_db, temp_tenants_yaml):
    tm = TenantManager(config_path=temp_tenants_yaml)
    n = tm.load_from_yaml()
    assert n == 2
    assert tm.has("tenant_0001")
    assert tm.has("tenant_0002")
    t1 = tm.get("tenant_0001")
    assert t1.boss_name == "连大哥"
    assert t1.daily_quota == 100
