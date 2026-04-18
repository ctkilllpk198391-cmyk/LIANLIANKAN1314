"""tests/test_activation.py · F2 激活码系统 ≥10 用例。"""

from __future__ import annotations

import time

import pytest
import pytest_asyncio

from server.activation import ActivationService, _OFFLINE_TTL_SECONDS


# ── 工具函数 ─────────────────────────────────────────────────────────────────

async def _make_code(svc: ActivationService, plan: str = "pro", valid_days: int = 365) -> str:
    return await svc.generate_code_async(plan=plan, valid_days=valid_days)


async def _activate(svc: ActivationService, code: str, tenant: str = "t001") -> str:
    return await svc.activate(code=code, machine_guid="GUID-1234", tenant_id=tenant)


# ── 1. 生成激活码格式正确 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_code_format(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    parts = code.split("-")
    assert parts[0] == "WXA"
    assert parts[1] == "2026"
    assert len(parts) == 5


# ── 2. 生成码唯一 ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_code_unique(temp_db):
    svc = ActivationService()
    codes = {await _make_code(svc) for _ in range(10)}
    assert len(codes) == 10


# ── 3. 正常激活 · 返回有效 token ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_activate_success(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    token = await _activate(svc, code)
    assert token and len(token) > 10


# ── 4. 激活后 is_valid 返回正确信息 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_is_valid_after_activate(temp_db):
    svc = ActivationService()
    code = await _make_code(svc, plan="flagship")
    token = await _activate(svc, code)
    info = await svc.is_valid(token)
    assert info is not None
    assert info["tenant_id"] == "t001"
    assert info["plan"] == "flagship"


# ── 5. 重复激活同一码报错 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_double_activate_raises(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    await _activate(svc, code)
    with pytest.raises(ValueError, match="already used"):
        await _activate(svc, code, tenant="t002")


# ── 6. 无效激活码报错 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_code_raises(temp_db):
    svc = ActivationService()
    with pytest.raises(ValueError, match="invalid activation code"):
        await svc.activate(code="WXA-2026-FAKE-CODE-999", machine_guid="G", tenant_id="t001")


# ── 7. 吊销激活码后无法激活 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_code_blocks_activate(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    await svc.revoke_code(code)
    with pytest.raises(ValueError, match="revoked"):
        await _activate(svc, code)


# ── 8. 心跳正常返回 True ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_ok(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    token = await _activate(svc, code)
    result = await svc.heartbeat(token)
    assert result is True


# ── 9. 吊销设备后心跳返回 False ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_revoked_device(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    token = await _activate(svc, code)
    await svc.revoke_device(token)
    result = await svc.heartbeat(token)
    assert result is False


# ── 10. 离线超 7 天心跳返回 False 并自动吊销 ────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_offline_too_long(temp_db, monkeypatch):
    svc = ActivationService()
    code = await _make_code(svc)
    token = await _activate(svc, code)

    # 模拟 last_heartbeat_at 在 8 天前
    from sqlalchemy import select
    from server.db import session_scope
    from server.models import DeviceBinding

    eight_days_ago = int(time.time()) - _OFFLINE_TTL_SECONDS - 3600
    async with session_scope() as session:
        row = (await session.execute(
            select(DeviceBinding).where(DeviceBinding.device_token == token)
        )).scalar_one()
        row.last_heartbeat_at = eight_days_ago

    result = await svc.heartbeat(token)
    assert result is False

    # is_valid 也应返回 None
    info = await svc.is_valid(token)
    assert info is None


# ── 11. machine_guid 为空时 sha256 兜底 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_activate_without_machine_guid(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    token = await svc.activate(code=code, machine_guid="", tenant_id="t001")
    info = await svc.is_valid(token)
    assert info is not None


# ── 12. 吊销激活码后 is_valid 返回 None ─────────────────────────────────────

@pytest.mark.asyncio
async def test_is_valid_revoked_code(temp_db):
    svc = ActivationService()
    code = await _make_code(svc)
    token = await _activate(svc, code)
    await svc.revoke_code(code)
    info = await svc.is_valid(token)
    assert info is None


# ── 13. 吊销不存在的激活码报错 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_nonexistent_code(temp_db):
    svc = ActivationService()
    with pytest.raises(ValueError, match="not found"):
        await svc.revoke_code("WXA-2026-DEAD-BEEF-NONE")


# ── 14. 吊销不存在的设备 token 报错 ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_nonexistent_device(temp_db):
    svc = ActivationService()
    with pytest.raises(ValueError, match="not found"):
        await svc.revoke_device("nonexistent_token_xyz")


# ── 15. 无效 token is_valid 返回 None ───────────────────────────────────────

@pytest.mark.asyncio
async def test_is_valid_unknown_token(temp_db):
    svc = ActivationService()
    info = await svc.is_valid("totally_fake_token")
    assert info is None


# ── 16. 不同 plan 正确存储 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_stored_correctly(temp_db):
    svc = ActivationService()
    code_trial = await _make_code(svc, plan="trial", valid_days=30)
    token = await svc.activate(code=code_trial, machine_guid="G", tenant_id="t_trial")
    info = await svc.is_valid(token)
    assert info["plan"] == "trial"
