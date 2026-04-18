"""dashboard.py 测试。"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_dashboard_empty_tenant(temp_db, loaded_tenants):
    from server.dashboard import DashboardBuilder

    db = DashboardBuilder()
    data = await db.build("tenant_0001")
    assert data["tenant_id"] == "tenant_0001"
    assert data["today"]["total_generated"] == 0
    assert data["today"]["acceptance_rate"] == 0.0
    assert data["quota"]["remaining"] == 100


@pytest.mark.asyncio
async def test_dashboard_via_api(app_client):
    r = await app_client.get("/v1/dashboard/tenant_0001")
    assert r.status_code == 200
    data = r.json()
    assert data["tenant_id"] == "tenant_0001"
    assert "today" in data
    assert "quota" in data


@pytest.mark.asyncio
async def test_dashboard_unknown_tenant_404(app_client):
    r = await app_client.get("/v1/dashboard/tenant_unknown_xyz")
    assert r.status_code == 404
