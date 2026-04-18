"""websocket_pusher.py 测试。"""

from __future__ import annotations

import asyncio

import pytest


class _FakeWS:
    def __init__(self, fail_send: bool = False):
        self.received: list[str] = []
        self.fail_send = fail_send

    async def accept(self):
        pass

    async def send_text(self, msg: str):
        if self.fail_send:
            raise ConnectionError("simulated dead conn")
        self.received.append(msg)


@pytest.mark.asyncio
async def test_connect_and_push():
    from server.websocket_pusher import ConnectionManager

    cm = ConnectionManager()
    ws = _FakeWS()
    await cm.connect(ws, "tenant_0001")
    n = await cm.push("tenant_0001", {"hello": "world"})
    assert n == 1
    assert "hello" in ws.received[0]


@pytest.mark.asyncio
async def test_push_to_no_connections():
    from server.websocket_pusher import ConnectionManager

    cm = ConnectionManager()
    n = await cm.push("tenant_nobody", {"x": 1})
    assert n == 0


@pytest.mark.asyncio
async def test_dead_connection_pruned():
    from server.websocket_pusher import ConnectionManager

    cm = ConnectionManager()
    ws_ok = _FakeWS()
    ws_dead = _FakeWS(fail_send=True)
    await cm.connect(ws_ok, "tenant_0001")
    await cm.connect(ws_dead, "tenant_0001")
    n = await cm.push("tenant_0001", {"a": 1})
    assert n == 1
    # dead 连接应被剪掉
    assert cm.active_count("tenant_0001") == 1


@pytest.mark.asyncio
async def test_disconnect():
    from server.websocket_pusher import ConnectionManager

    cm = ConnectionManager()
    ws = _FakeWS()
    await cm.connect(ws, "tenant_0001")
    assert cm.active_count("tenant_0001") == 1
    await cm.disconnect(ws, "tenant_0001")
    assert cm.active_count("tenant_0001") == 0
