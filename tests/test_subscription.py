"""subscription.py 生命周期测试。"""

from __future__ import annotations

import time

import pytest


@pytest.mark.asyncio
async def test_activate_pro(temp_db, loaded_tenants):
    from server.subscription import SubscriptionService

    svc = SubscriptionService()
    sub = await svc.activate("tenant_0001", "pro", months=1)
    assert sub.tenant_id == "tenant_0001"
    assert sub.plan == "pro"
    assert sub.status == "active"
    assert sub.expires_at > sub.started_at


@pytest.mark.asyncio
async def test_is_active_true_then_false(temp_db, loaded_tenants):
    from server.subscription import SECONDS_PER_MONTH, SubscriptionService

    svc = SubscriptionService()
    await svc.activate("tenant_0001", "pro", months=1)
    assert await svc.is_active("tenant_0001") is True
    assert await svc.is_active("tenant_0002") is False


@pytest.mark.asyncio
async def test_renew_extends_expiry(temp_db, loaded_tenants):
    from server.subscription import SECONDS_PER_MONTH, SubscriptionService

    svc = SubscriptionService()
    s1 = await svc.activate("tenant_0001", "pro", months=1)
    s2 = await svc.activate("tenant_0001", "pro", months=2)
    # s2 起点应为 s1 的 expires_at（叠加而非覆盖）
    assert s2.started_at == s1.expires_at
    assert s2.expires_at == s1.expires_at + 2 * SECONDS_PER_MONTH


@pytest.mark.asyncio
async def test_cancel(temp_db, loaded_tenants):
    from server.subscription import SubscriptionService

    svc = SubscriptionService()
    await svc.activate("tenant_0001", "pro", months=1)
    await svc.cancel("tenant_0001")
    assert await svc.is_active("tenant_0001") is False


@pytest.mark.asyncio
async def test_expiring_soon(temp_db, loaded_tenants):
    from server.subscription import SubscriptionService

    svc = SubscriptionService()
    await svc.activate("tenant_0001", "pro", months=1)
    soon = await svc.expiring_soon(days=60)  # 60 天内全部覆盖
    assert "tenant_0001" in soon
