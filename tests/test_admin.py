"""tests/test_admin.py · FDW F6 管理后台测试 · ≥6 用例。"""

from __future__ import annotations

import os
import time

import pytest

# ─── 辅助 fixture ────────────────────────────────────────────────────────────

ADMIN_TOKEN = "test-admin-token-fdw-f6"


@pytest.fixture(autouse=True)
def set_admin_token(monkeypatch):
    """为每个测试注入 ADMIN_TOKEN 环境变量（覆盖 server.admin 模块级变量）。"""
    monkeypatch.setenv("BAIYANG_ADMIN_TOKEN", ADMIN_TOKEN)
    # 重新加载 admin 模块使环境变量生效
    import importlib
    import server.admin as adm
    monkeypatch.setattr(adm, "ADMIN_TOKEN", ADMIN_TOKEN)


# ─── 单元测试：AdminService ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_issue_code_format(temp_db):
    """issue_activation_code 返回合法格式的激活码。"""
    from server.admin import AdminService
    svc = AdminService()
    code = await svc.issue_activation_code(plan="pro", valid_days=365)
    # 格式: WXA-XXXX-XXXX-XXXX-XXXX
    parts = code.split("-")
    assert parts[0] == "WXA"
    assert len(parts) == 5
    for p in parts[1:]:
        assert len(p) == 4


@pytest.mark.asyncio
async def test_issue_code_persisted(temp_db):
    """issue_activation_code 入库后 list_customers 可见设备统计。"""
    from server.admin import AdminService
    svc = AdminService()
    code = await svc.issue_activation_code(plan="trial", valid_days=30)
    assert code.startswith("WXA-")
    # 数据库里能查到激活码
    from server.db import session_scope
    from server.models import ActivationCode
    from sqlalchemy import select
    async with session_scope() as session:
        row = (await session.execute(
            select(ActivationCode).where(ActivationCode.code == code)
        )).scalar_one_or_none()
    assert row is not None
    assert row.plan == "trial"
    assert row.valid_days == 30
    assert row.revoked == 0


@pytest.mark.asyncio
async def test_revoke_code(temp_db):
    """revoke_code 将激活码标记为已撤销。"""
    from server.admin import AdminService
    svc = AdminService()
    code = await svc.issue_activation_code(plan="pro", valid_days=365)
    await svc.revoke_code(code)

    from server.db import session_scope
    from server.models import ActivationCode
    from sqlalchemy import select
    async with session_scope() as session:
        row = (await session.execute(
            select(ActivationCode).where(ActivationCode.code == code)
        )).scalar_one_or_none()
    assert row is not None
    assert row.revoked == 1


@pytest.mark.asyncio
async def test_revoke_code_not_found(temp_db):
    """revoke_code 对不存在的码抛 404。"""
    from fastapi import HTTPException
    from server.admin import AdminService
    svc = AdminService()
    with pytest.raises(HTTPException) as exc_info:
        await svc.revoke_code("WXA-FAKE-FAKE-FAKE-FAKE")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_list_customers_empty(temp_db):
    """无客户时 list_customers 返回空列表。"""
    from server.admin import AdminService
    svc = AdminService()
    result = await svc.list_customers()
    assert isinstance(result, list)
    assert len(result) == 0


@pytest.mark.asyncio
async def test_health_overview_structure(temp_db):
    """health_overview 返回合法结构。"""
    from server.admin import AdminService
    svc = AdminService()
    overview = await svc.health_overview()
    assert "total_tenants" in overview
    assert "online_devices" in overview
    assert "total_devices" in overview
    assert "total_activation_codes" in overview
    assert "activated_codes" in overview
    assert isinstance(overview["timestamp"], int)


@pytest.mark.asyncio
async def test_export_revenue_report(temp_db):
    """export_revenue_report 返回合法结构。"""
    from server.admin import AdminService
    svc = AdminService()
    report = await svc.export_revenue_report("2026-01-01", "2026-12-31")
    assert report["start_date"] == "2026-01-01"
    assert report["end_date"] == "2026-12-31"
    assert "codes_issued" in report
    assert "codes_activated" in report
    assert "plans" in report
    assert isinstance(report["plans"], dict)


# ─── API 路由测试（通过 app_client） ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_customers_no_token(app_client):
    """未携带 X-Admin-Token 时 GET /admin/customers 返回 401。"""
    r = await app_client.get("/admin/customers")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_customers_wrong_token(app_client):
    """携带错误 token 时返回 401。"""
    r = await app_client.get(
        "/admin/customers",
        headers={"X-Admin-Token": "wrong-token-xxx"},
    )
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_admin_customers_valid_token(app_client, monkeypatch):
    """携带正确 token 返回 200 且结果是列表。"""
    import server.admin as adm
    monkeypatch.setattr(adm, "ADMIN_TOKEN", ADMIN_TOKEN)
    r = await app_client.get(
        "/admin/customers",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_admin_issue_code_api(app_client, monkeypatch):
    """POST /admin/issue_code 返回正确格式激活码。"""
    import server.admin as adm
    monkeypatch.setattr(adm, "ADMIN_TOKEN", ADMIN_TOKEN)
    r = await app_client.post(
        "/admin/issue_code",
        headers={"X-Admin-Token": ADMIN_TOKEN},
        json={"plan": "flagship", "valid_days": 365},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["code"].startswith("WXA-")
    assert body["plan"] == "flagship"


@pytest.mark.asyncio
async def test_admin_revoke_api(app_client, monkeypatch):
    """POST /admin/revoke/{code} 正常撤销已存在的码。"""
    import server.admin as adm
    monkeypatch.setattr(adm, "ADMIN_TOKEN", ADMIN_TOKEN)

    # 先发一张码
    issue_r = await app_client.post(
        "/admin/issue_code",
        headers={"X-Admin-Token": ADMIN_TOKEN},
        json={"plan": "pro", "valid_days": 30},
    )
    code = issue_r.json()["code"]

    # 再撤销
    revoke_r = await app_client.post(
        f"/admin/revoke/{code}",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert revoke_r.status_code == 200
    assert revoke_r.json()["ok"] is True


@pytest.mark.asyncio
async def test_admin_health_overview_api(app_client, monkeypatch):
    """GET /admin/health/overview 返回合法结构。"""
    import server.admin as adm
    monkeypatch.setattr(adm, "ADMIN_TOKEN", ADMIN_TOKEN)
    r = await app_client.get(
        "/admin/health/overview",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert r.status_code == 200
    body = r.json()
    assert "total_tenants" in body
    assert "online_devices" in body


@pytest.mark.asyncio
async def test_admin_revenue_api(app_client, monkeypatch):
    """GET /admin/revenue 返回报表结构。"""
    import server.admin as adm
    monkeypatch.setattr(adm, "ADMIN_TOKEN", ADMIN_TOKEN)
    r = await app_client.get(
        "/admin/revenue?start_date=2026-01-01&end_date=2026-12-31",
        headers={"X-Admin-Token": ADMIN_TOKEN},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["start_date"] == "2026-01-01"
    assert "codes_issued" in body


# ─── Sentry 集成 smoke test ──────────────────────────────────────────────────

def test_server_sentry_init_no_dsn(monkeypatch):
    """SENTRY_DSN 未设置时 init_sentry 返回 False 不崩溃。"""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    from server.sentry_init import init_sentry
    result = init_sentry(release="test")
    assert result is False


def test_client_sentry_init_no_dsn(monkeypatch):
    """客户端 SENTRY_DSN 未设置时 init_sentry 返回 False 不崩溃。"""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    from client.sentry_init import init_sentry
    result = init_sentry(release="test")
    assert result is False


def test_sentry_capture_exception_no_sdk():
    """sentry-sdk 未安装时 capture_exception 静默不崩溃。"""
    from server.sentry_init import capture_exception
    # 无论 sdk 是否安装，调用不应抛出
    capture_exception(ValueError("test error"), tenant_id="tenant_0001")
