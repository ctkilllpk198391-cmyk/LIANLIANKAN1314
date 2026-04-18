"""WebSocket 推送 · 客户端实时拉 suggestion · 替代 Phase 1 长轮询。"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """每 tenant 维护一组 active connections · push 时广播。"""

    def __init__(self):
        self._conns: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, tenant_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._conns[tenant_id].add(ws)
        logger.info("ws connected · tenant=%s · total=%d", tenant_id, len(self._conns[tenant_id]))

    async def disconnect(self, ws: WebSocket, tenant_id: str) -> None:
        async with self._lock:
            self._conns[tenant_id].discard(ws)
        logger.info("ws disconnected · tenant=%s · total=%d", tenant_id, len(self._conns[tenant_id]))

    async def push(self, tenant_id: str, payload: dict[str, Any]) -> int:
        msg = json.dumps(payload, ensure_ascii=False)
        sent = 0
        dead: list[WebSocket] = []
        async with self._lock:
            conns = list(self._conns.get(tenant_id, set()))
        for ws in conns:
            try:
                await ws.send_text(msg)
                sent += 1
            except Exception as e:
                logger.warning("ws push failed · drop: %s", e)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._conns[tenant_id].discard(ws)
        return sent

    def active_count(self, tenant_id: str) -> int:
        return len(self._conns.get(tenant_id, set()))


manager = ConnectionManager()


async def websocket_endpoint(ws: WebSocket, tenant_id: str) -> None:
    await manager.connect(ws, tenant_id)
    try:
        while True:
            data = await ws.receive_text()
            # 客户端可发 ping 保活
            if data == "ping":
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(ws, tenant_id)
