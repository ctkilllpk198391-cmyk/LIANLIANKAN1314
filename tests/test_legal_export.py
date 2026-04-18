"""L4 · 律师举证包导出测试。"""

from __future__ import annotations

import time

import pytest

from server.audit import audit
from server.db import session_scope
from server.legal_export import LegalExporter
from server.models import Tenant


@pytest.mark.asyncio
async def test_export_for_tenant_basic(temp_db):
    # 建 tenant
    async with session_scope() as s:
        s.add(Tenant(tenant_id="tenant_x", boss_name="测试老板", plan="pro", created_at=int(time.time())))

    # 写几条 audit
    await audit.log(actor="client", action="consent_signed", tenant_id="tenant_x", meta={"version": "v3"})
    await audit.log(actor="server", action="auto_send_auto_send", tenant_id="tenant_x", msg_id="sug_001")
    await audit.log(actor="boss", action="auto_send_paused", tenant_id="tenant_x", meta={"until": 9999})

    exporter = LegalExporter()
    pkg = await exporter.export_for_tenant("tenant_x")

    assert pkg.tenant_id == "tenant_x"
    assert pkg.boss_name == "测试老板"
    assert pkg.plan == "pro"
    assert "consent_signed" in pkg.audit_log_csv
    assert "auto_send_paused" in pkg.audit_log_csv
    assert len(pkg.consent_records) >= 1
    assert len(pkg.auto_send_config_history) >= 1
    assert "tenant_x" in pkg.tenant_summary_md


@pytest.mark.asyncio
async def test_export_with_time_range(temp_db):
    async with session_scope() as s:
        s.add(Tenant(tenant_id="tenant_y", boss_name="老板", plan="trial", created_at=int(time.time())))

    now = int(time.time())
    # 写 3 条 audit 在不同时间
    await audit.log(actor="x", action="early", tenant_id="tenant_y", meta={"t": "old"})

    exporter = LegalExporter()
    pkg = await exporter.export_for_tenant("tenant_y", start_ts=now - 86400, end_ts=now + 86400)
    assert "tenant_y" in pkg.audit_log_csv


@pytest.mark.asyncio
async def test_export_empty_tenant_works(temp_db):
    async with session_scope() as s:
        s.add(Tenant(tenant_id="tenant_empty", boss_name="老板", plan="trial", created_at=int(time.time())))

    exporter = LegalExporter()
    pkg = await exporter.export_for_tenant("tenant_empty")
    assert pkg.tenant_id == "tenant_empty"
    assert pkg.audit_log_csv  # csv 含 header


@pytest.mark.asyncio
async def test_export_summary_contains_legal_meaning(temp_db):
    async with session_scope() as s:
        s.add(Tenant(tenant_id="tenant_z", boss_name="老板", plan="pro", created_at=int(time.time())))

    exporter = LegalExporter()
    pkg = await exporter.export_for_tenant("tenant_z")
    assert "v3 协议" in pkg.tenant_summary_md
    assert "客户" in pkg.tenant_summary_md
    assert "证据链" in pkg.tenant_summary_md
