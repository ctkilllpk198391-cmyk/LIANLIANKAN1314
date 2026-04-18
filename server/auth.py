"""FDW F5 · Web 鉴权 · FastAPI dependency + AuthContext。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException, Request

from server.activation import ActivationService

_svc = ActivationService()


@dataclass
class AuthContext:
    tenant_id: str
    device_token: str
    plan: str


async def auth_required(request: Request) -> AuthContext:
    """FastAPI dependency · Bearer <device_token> 校验 · 失败 401。

    backward compat：X-Test-Mode: bypass → 跳过鉴权（测试专用）。
    直接调用时可传 mock_request；单测通过 _auth_from_headers() 调用。
    """
    authorization = request.headers.get("authorization") or request.headers.get("Authorization")
    x_test_mode = request.headers.get("x-test-mode") or request.headers.get("X-Test-Mode")
    return await _auth_from_headers(authorization=authorization, x_test_mode=x_test_mode)


async def _auth_from_headers(
    authorization: Optional[str] = None,
    x_test_mode: Optional[str] = None,
) -> AuthContext:
    """核心鉴权逻辑 · 可被测试直接调用。"""
    if x_test_mode and x_test_mode.lower() == "bypass":
        return AuthContext(tenant_id="test_tenant", device_token="test_token", plan="pro")

    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format, expected Bearer <token>")

    token = authorization[len("Bearer "):]
    if not token.strip():
        raise HTTPException(status_code=401, detail="Empty bearer token")

    info = await _svc.is_valid(token)
    if info is None:
        raise HTTPException(status_code=401, detail="Invalid or revoked device token")

    return AuthContext(
        tenant_id=info["tenant_id"],
        device_token=token,
        plan=info["plan"],
    )
