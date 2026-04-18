"""F7 · 多账号容灾测试。"""

from __future__ import annotations

import pytest

from server.account_failover import AccountFailover
from server.health_monitor import HealthMonitor
from server.tenant import TenantManager
from shared.proto import TenantConfig


def _mk_tenant_manager_with_accounts():
    tm = TenantManager()
    tm._cache["tenant_0001"] = TenantConfig(
        tenant_id="tenant_0001",
        boss_name="连大哥",
        accounts=[
            {"account_id": "acc_primary", "role": "primary", "wxid": "wxid_p"},
            {"account_id": "acc_secondary", "role": "secondary", "wxid": "wxid_s"},
        ],
        active_account_id="acc_primary",
    )
    tm._cache["tenant_solo"] = TenantConfig(
        tenant_id="tenant_solo",
        boss_name="单号老板",
        accounts=[],
    )
    return tm


@pytest.mark.asyncio
async def test_get_active_default_primary(temp_db):
    tm = _mk_tenant_manager_with_accounts()
    fo = AccountFailover(tm, HealthMonitor())
    assert fo.get_active_account_id("tenant_0001") == "acc_primary"


@pytest.mark.asyncio
async def test_list_accounts_returns_all(temp_db):
    tm = _mk_tenant_manager_with_accounts()
    fo = AccountFailover(tm, HealthMonitor())
    accounts = await fo.list_accounts("tenant_0001")
    assert len(accounts) == 2
    active = next(a for a in accounts if a.is_active)
    assert active.account_id == "acc_primary"


@pytest.mark.asyncio
async def test_manual_switch_succeeds(temp_db):
    tm = _mk_tenant_manager_with_accounts()
    fo = AccountFailover(tm, HealthMonitor())
    ok = await fo.manual_switch("tenant_0001", "acc_secondary")
    assert ok
    assert fo.get_active_account_id("tenant_0001") == "acc_secondary"


@pytest.mark.asyncio
async def test_manual_switch_invalid_target(temp_db):
    tm = _mk_tenant_manager_with_accounts()
    fo = AccountFailover(tm, HealthMonitor())
    ok = await fo.manual_switch("tenant_0001", "acc_nonexistent")
    assert not ok


@pytest.mark.asyncio
async def test_auto_failover_picks_green(temp_db):
    tm = _mk_tenant_manager_with_accounts()
    health = HealthMonitor()
    # secondary 没有任何记录 → 默认 green
    fo = AccountFailover(tm, health)
    new_active = await fo.auto_failover("tenant_0001", "acc_primary", reason="health red")
    assert new_active == "acc_secondary"
    assert fo.get_active_account_id("tenant_0001") == "acc_secondary"


@pytest.mark.asyncio
async def test_auto_failover_no_backup_returns_none(temp_db):
    tm = _mk_tenant_manager_with_accounts()
    fo = AccountFailover(tm, HealthMonitor())
    result = await fo.auto_failover("tenant_solo", "primary", reason="x")
    assert result is None


@pytest.mark.asyncio
async def test_failover_history_records(temp_db):
    tm = _mk_tenant_manager_with_accounts()
    fo = AccountFailover(tm, HealthMonitor())
    await fo.manual_switch("tenant_0001", "acc_secondary")
    history = await fo.history("tenant_0001")
    assert len(history) == 1
    assert history[0]["from"] == "acc_primary"
    assert history[0]["to"] == "acc_secondary"
    assert history[0]["auto"] is False
