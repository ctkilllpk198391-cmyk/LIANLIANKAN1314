"""tests/test_auth.py · F5 Web 鉴权 ≥6 用例。"""

from __future__ import annotations

import pytest

from fastapi import HTTPException

from server.auth import _auth_from_headers, AuthContext


async def _make_valid_token(temp_db: str) -> tuple[str, str]:
    """生成并激活一个激活码，返回 (token, plan)。"""
    from server.activation import ActivationService
    svc = ActivationService()
    code = await svc.generate_code_async(plan="pro", valid_days=365)
    token = await svc.activate(code=code, machine_guid="GUID-TEST", tenant_id="auth_tenant")
    return token, "pro"


# ── 1. 有效 Bearer token 通过鉴权 ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_valid_token(temp_db):
    token, plan = await _make_valid_token(temp_db)
    ctx = await _auth_from_headers(authorization=f"Bearer {token}")
    assert isinstance(ctx, AuthContext)
    assert ctx.tenant_id == "auth_tenant"
    assert ctx.plan == plan
    assert ctx.device_token == token


# ── 2. 无 Authorization header → 401 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_token(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await _auth_from_headers(authorization=None)
    assert exc_info.value.status_code == 401


# ── 3. 无效 token → 401 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalid_token(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await _auth_from_headers(authorization="Bearer completely_fake_token")
    assert exc_info.value.status_code == 401


# ── 4. 吊销 token → 401 ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoked_token(temp_db):
    from server.activation import ActivationService
    svc = ActivationService()
    token, _ = await _make_valid_token(temp_db)
    await svc.revoke_device(token)

    with pytest.raises(HTTPException) as exc_info:
        await _auth_from_headers(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


# ── 5. 格式错误（无 Bearer 前缀）→ 401 ──────────────────────────────────────

@pytest.mark.asyncio
async def test_wrong_format(temp_db):
    token, _ = await _make_valid_token(temp_db)
    with pytest.raises(HTTPException) as exc_info:
        await _auth_from_headers(authorization=token)  # 缺少 Bearer 前缀
    assert exc_info.value.status_code == 401


# ── 6. X-Test-Mode: bypass 跳过鉴权 ────────────────────────────────────────

@pytest.mark.asyncio
async def test_test_mode_bypass(temp_db):
    ctx = await _auth_from_headers(authorization=None, x_test_mode="bypass")
    assert ctx.tenant_id == "test_tenant"
    assert ctx.plan == "pro"


# ── 7. Bearer 后空 token → 401 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_bearer_token(temp_db):
    with pytest.raises(HTTPException) as exc_info:
        await _auth_from_headers(authorization="Bearer ")
    assert exc_info.value.status_code == 401


# ── 8. 吊销激活码后 token → 401 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoked_code_invalidates_token(temp_db):
    from server.activation import ActivationService
    svc = ActivationService()
    code = await svc.generate_code_async(plan="pro", valid_days=365)
    token = await svc.activate(code=code, machine_guid="G", tenant_id="t_revoke")
    await svc.revoke_code(code)

    with pytest.raises(HTTPException) as exc_info:
        await _auth_from_headers(authorization=f"Bearer {token}")
    assert exc_info.value.status_code == 401


# ── 9. X-Test-Mode 大小写不敏感 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_test_mode_case_insensitive(temp_db):
    ctx = await _auth_from_headers(authorization=None, x_test_mode="BYPASS")
    assert ctx.tenant_id == "test_tenant"
