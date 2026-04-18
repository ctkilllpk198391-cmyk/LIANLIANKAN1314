"""WebSocket endpoint 测试 · 完整 ws 路由。"""

from __future__ import annotations

import json

import pytest


@pytest.mark.asyncio
async def test_ws_endpoint_routed(app_client):
    """验证 /v1/ws/{tenant} 路由已挂在 app 上。"""
    # ASGITransport 不支持 ws upgrade · 用 TestClient 替代
    from fastapi.testclient import TestClient

    from server.main import app

    # 取出 routes 验证
    paths = [r.path for r in app.routes if hasattr(r, "path")]
    assert "/v1/ws/{tenant_id}" in paths or "/v1/ws/{tenant_id}/" in paths


@pytest.mark.asyncio
async def test_ws_pusher_isolation():
    """tenant_a 的连接不接收 tenant_b 的推送。"""
    from server.websocket_pusher import ConnectionManager

    class FakeWS:
        def __init__(self):
            self.received = []
        async def accept(self): pass
        async def send_text(self, msg): self.received.append(msg)

    cm = ConnectionManager()
    a = FakeWS()
    b = FakeWS()
    await cm.connect(a, "tenant_a")
    await cm.connect(b, "tenant_b")
    await cm.push("tenant_a", {"only_for": "a"})
    assert len(a.received) == 1
    assert len(b.received) == 0
