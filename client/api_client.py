"""APIClient · 客户端调用服务端的 HTTP 接口。"""

from __future__ import annotations

import logging
from typing import Optional

import aiohttp

from shared.proto import InboundMsg, ReviewDecision, SendAck, Suggestion

logger = logging.getLogger(__name__)


class ServerAPIClient:
    def __init__(self, base_url: str, timeout_sec: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = aiohttp.ClientTimeout(total=timeout_sec)

    async def submit_inbound(self, msg: InboundMsg) -> Suggestion:
        url = f"{self.base_url}/v1/inbound"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, json=msg.model_dump()) as resp:
                resp.raise_for_status()
                return Suggestion.model_validate(await resp.json())

    async def submit_decision(self, decision: ReviewDecision) -> dict:
        url = f"{self.base_url}/v1/outbound/{decision.msg_id}/decide"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, json=decision.model_dump()) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def submit_send_ack(self, ack: SendAck) -> dict:
        url = f"{self.base_url}/v1/outbound/{ack.msg_id}/sent"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(url, json=ack.model_dump()) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def fetch_pending(self, tenant_id: str, limit: int = 20) -> list[dict]:
        url = f"{self.base_url}/v1/outbound/pending/{tenant_id}?limit={limit}"
        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.get(url) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def health(self) -> Optional[dict]:
        url = f"{self.base_url}/v1/health"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.warning("health check failed: %s", e)
        return None
