"""客户端主入口 · 串联 watcher → review_popup → sender。

用法：
  python -m client.main --tenant tenant_0001 --server http://127.0.0.1:8327
  python -m client.main --tenant tenant_0001 --mock      # macOS 调试模式
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import platform
import sys

from client.api_client import ServerAPIClient
from client.review_popup import ConsoleReviewPopup, HeadlessAutoAccept
from client.risk_control import RiskController, WorkSchedule
from client.sender import HumanLikeSender
from client.version_probe import detect_wechat_version
from client.watcher import WeChatWatcher
from shared.proto import ReviewDecision, SendAck, Suggestion
from shared.types import ReviewDecisionEnum

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("baiyang.client")


class ClientApp:
    def __init__(
        self,
        server_url: str,
        tenant_id: str,
        mock: bool = False,
        auto_accept: bool = False,
    ):
        self.server_url = server_url
        self.tenant_id = tenant_id
        self.mock = mock
        self.api = ServerAPIClient(server_url)
        self.risk = RiskController()
        self.risk.register(tenant_id, daily_quota=100, schedule=WorkSchedule())
        self.sender = HumanLikeSender(mock=mock)

        if auto_accept:
            self.popup = HeadlessAutoAccept(self._submit_decision)
        else:
            self.popup = ConsoleReviewPopup(self._submit_decision)

        self.watcher = WeChatWatcher(
            server_url=server_url,
            tenant_id=tenant_id,
            mock=mock,
            on_suggestion=self._on_suggestion,
        )

    async def _submit_decision(self, decision: ReviewDecision) -> dict:
        return await self.api.submit_decision(decision)

    async def _on_suggestion(self, suggestion: Suggestion) -> None:
        if not self.risk.can_send(self.tenant_id):
            logger.warning(
                "msg %s 跳过：当前非工作时间或配额已耗尽 (剩余 %d)",
                suggestion.msg_id,
                self.risk.quota_remaining(self.tenant_id),
            )
            decision = ReviewDecision(
                msg_id=suggestion.msg_id,
                decision=ReviewDecisionEnum.REJECT,
                reviewed_at=int(asyncio.get_event_loop().time()),
            )
            await self._submit_decision(decision)
            return

        decision = await self.popup.show(suggestion)
        if decision.decision == ReviewDecisionEnum.REJECT:
            logger.info("msg %s 老板拒绝", suggestion.msg_id)
            return

        text_to_send = decision.edited_text or suggestion.text
        chat_id_for_send = await self._lookup_chat_id(suggestion.msg_id) or "unknown"

        try:
            self.risk.consume(self.tenant_id)
        except Exception as e:
            logger.warning("发送被风控拦截: %s", e)
            return

        ack = await self.sender.send(chat_id_for_send, text_to_send)
        await self.api.submit_send_ack(SendAck(
            msg_id=suggestion.msg_id,
            sent_at=ack.sent_at,
            success=ack.success,
            error=ack.error,
        ))

    async def _lookup_chat_id(self, msg_id: str) -> str | None:
        # 真实场景下 server 应该在 Suggestion 里带上 chat_id
        # Phase 1 从 pending 反查（占位）
        items = await self.api.fetch_pending(self.tenant_id, limit=20)
        for it in items:
            if it.get("msg_id") == msg_id:
                return it.get("chat_id")
        return None

    async def run(self) -> None:
        health = await self.api.health()
        if not health:
            logger.error("server 不可达：%s · 请先启动 server", self.server_url)
            sys.exit(1)
        logger.info("server health: %s", health)

        if not self.mock:
            v = detect_wechat_version()
            logger.info("WeChat PC 版本: %s (mock=%s)", v or "未知", self.mock)

        logger.info("wechat_agent 客户端启动 · tenant=%s · server=%s · mock=%s",
                    self.tenant_id, self.server_url, self.mock)
        await self.watcher.start()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="baiyang-client")
    p.add_argument("--tenant", required=True, help="tenant_id (如 tenant_0001)")
    p.add_argument("--server", default="http://127.0.0.1:8327", help="server URL")
    p.add_argument("--mock", action="store_true", help="mock 模式 · macOS 调试")
    p.add_argument("--auto-accept", action="store_true", help="无人值守自动 accept (仅测试)")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not args.mock and platform.system() != "Windows":
        logger.warning("非 Windows 环境，强制启用 --mock")
        args.mock = True

    app = ClientApp(
        server_url=args.server,
        tenant_id=args.tenant,
        mock=args.mock,
        auto_accept=args.auto_accept,
    )
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C · 退出")


if __name__ == "__main__":
    main()
