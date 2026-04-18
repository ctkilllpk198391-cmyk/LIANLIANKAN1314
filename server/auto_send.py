"""F1 · 全自动决策引擎 · suggestion 生成后由它决定走全自动直发还是熔断。

5 种 decision：
  - auto_send       默认 · 全自动直发 · WS 推送 client.sender 立即发
  - blocked_high_risk  risk=HIGH + tenant.high_risk_block=True · 不发 · 推老板
  - blocked_paused  tenant 处于暂停期 · 不发 · 不推（老板自己暂停的）
  - blocked_unhealthy  account_health.level=red · 不发 · 推老板（容灾 F7 接管）
  - review_required tenant.auto_send_enabled=False · 进审核队列（兼容老路径）

外部组件可注入：
  - notifier: BossNotifier（默认 get_default_notifier）
  - ws_pusher: 异步可调用 (tenant_id, payload) → coroutine

设计原则：
  - 决策与执行分离：decide() 只返 decision · trigger_send() 才推 WS
  - 异步通知不阻塞主链路：notify_boss() 走 fire-and-forget
  - 暂停状态走 in-memory（重启即恢复 · 暂停最多 1 小时 · 重启相当于自然超时）
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional

from server.notifier import BossNotifier, get_default_notifier
from shared.proto import Suggestion, TenantConfig
from shared.types import RiskEnum

logger = logging.getLogger(__name__)


class AutoSendDecisionType(str, Enum):
    AUTO_SEND = "auto_send"
    BLOCKED_HIGH_RISK = "blocked_high_risk"
    BLOCKED_PAUSED = "blocked_paused"
    BLOCKED_UNHEALTHY = "blocked_unhealthy"
    REVIEW_REQUIRED = "review_required"


@dataclass
class AutoSendDecision:
    decision: AutoSendDecisionType
    suggestion: Suggestion
    reason: str = ""
    paused_until: Optional[int] = None
    health_score: Optional[float] = None
    metadata: dict = field(default_factory=dict)


WSPusher = Callable[[str, dict], Awaitable[None]]


class AutoSendDecider:
    """全自动决策核心。"""

    def __init__(
        self,
        notifier: Optional[BossNotifier] = None,
        ws_pusher: Optional[WSPusher] = None,
    ):
        self.notifier = notifier or get_default_notifier()
        self.ws_pusher = ws_pusher
        self._pause_state: dict[str, int] = {}   # tenant_id → pause_until_ts

    # ─── 暂停管理 ───────────────────────────────────────────────────────────

    def pause(self, tenant_id: str, duration_sec: int = 3600) -> int:
        until = int(time.time()) + max(60, min(duration_sec, 86400))
        self._pause_state[tenant_id] = until
        logger.warning("auto_send paused tenant=%s until=%d", tenant_id, until)
        return until

    def resume(self, tenant_id: str) -> bool:
        if tenant_id in self._pause_state:
            del self._pause_state[tenant_id]
            logger.info("auto_send resumed tenant=%s", tenant_id)
            return True
        return False

    def is_paused(self, tenant_id: str) -> bool:
        until = self._pause_state.get(tenant_id)
        if until is None:
            return False
        if time.time() >= until:
            del self._pause_state[tenant_id]
            return False
        return True

    def get_pause_until(self, tenant_id: str) -> Optional[int]:
        if not self.is_paused(tenant_id):
            return None
        return self._pause_state.get(tenant_id)

    # ─── 核心决策 ───────────────────────────────────────────────────────────

    async def decide(
        self,
        suggestion: Suggestion,
        tenant: TenantConfig,
        health_score: Optional[float] = None,
        health_level: Optional[str] = None,
    ) -> AutoSendDecision:
        # 1. 暂停优先
        if self.is_paused(tenant.tenant_id):
            return AutoSendDecision(
                decision=AutoSendDecisionType.BLOCKED_PAUSED,
                suggestion=suggestion,
                reason="老板手动暂停中",
                paused_until=self.get_pause_until(tenant.tenant_id),
            )

        # 2. 健康红灯
        if health_level == "red":
            return AutoSendDecision(
                decision=AutoSendDecisionType.BLOCKED_UNHEALTHY,
                suggestion=suggestion,
                reason=f"账号健康分 {health_score:.0f}/100 · 红灯",
                health_score=health_score,
            )

        # 3. 高风险熔断
        if (
            tenant.high_risk_block
            and suggestion.intent.risk == RiskEnum.HIGH
        ):
            return AutoSendDecision(
                decision=AutoSendDecisionType.BLOCKED_HIGH_RISK,
                suggestion=suggestion,
                reason=f"高风险消息（{suggestion.intent.intent.value}）熔断",
            )

        # 4. tenant 关闭全自动 → 兼容老路径走审核
        if not tenant.auto_send_enabled:
            return AutoSendDecision(
                decision=AutoSendDecisionType.REVIEW_REQUIRED,
                suggestion=suggestion,
                reason="auto_send_enabled=False · 走审核队列",
            )

        # 5. 默认 · 全自动直发
        return AutoSendDecision(
            decision=AutoSendDecisionType.AUTO_SEND,
            suggestion=suggestion,
            reason="auto",
            health_score=health_score,
        )

    # ─── 执行 ───────────────────────────────────────────────────────────────

    async def trigger_send(self, decision: AutoSendDecision, account_id: str = "primary") -> None:
        """根据决策推送 WS event 给 client。"""
        if decision.decision != AutoSendDecisionType.AUTO_SEND:
            logger.debug("trigger_send skipped: decision=%s", decision.decision.value)
            return

        if self.ws_pusher is None:
            logger.warning("trigger_send: ws_pusher is None · suggestion=%s", decision.suggestion.msg_id)
            return

        # SDW S1 节奏拟人：拆段 + 算每段 typing_delay
        from server.message_splitter import split_messages
        from server.typing_pacer import pace_segments

        text = decision.suggestion.text
        segments_text = split_messages(text)
        paced = pace_segments(segments_text) if segments_text else []

        payload = {
            "type": "auto_send_command",
            "msg_id": decision.suggestion.msg_id,
            "tenant_id": decision.suggestion.tenant_id,
            "account_id": account_id,
            "text": text,                 # backward compat · 整段
            "segments": [                  # SDW S1 · 节奏拟人
                {"text": p.text, "delay_ms": p.delay_ms} for p in paced
            ],
            "issued_at": int(time.time()),
        }
        try:
            await self.ws_pusher(decision.suggestion.tenant_id, payload)
        except Exception as e:
            logger.error("ws push failed: %s", e)

    async def notify_boss(
        self,
        decision: AutoSendDecision,
        tenant: TenantConfig,
        title: str,
        body: str,
    ) -> None:
        """异步推老板（不阻塞主链路）。"""
        webhook = tenant.boss_phone_webhook
        try:
            await self.notifier.notify(
                tenant_id=tenant.tenant_id,
                title=title,
                body=body,
                webhook=webhook,
            )
        except Exception as e:
            logger.error("notify_boss failed: %s", e)

    async def handle_decision(
        self,
        decision: AutoSendDecision,
        tenant: TenantConfig,
        account_id: str = "primary",
    ) -> None:
        """统一后处理 · 路由到 trigger_send / notify_boss。"""
        if decision.decision == AutoSendDecisionType.AUTO_SEND:
            await self.trigger_send(decision, account_id)
            return

        if decision.decision == AutoSendDecisionType.BLOCKED_HIGH_RISK:
            asyncio.create_task(
                self.notify_boss(
                    decision, tenant,
                    title="🚨 高风险消息熔断",
                    body=(
                        f"客户：{decision.suggestion.inbound_msg_id}\n"
                        f"意图：{decision.suggestion.intent.intent.value}\n"
                        f"AI 草稿：{decision.suggestion.text[:100]}\n"
                        f"已暂不发送 · 等你处理"
                    ),
                )
            )
            return

        if decision.decision == AutoSendDecisionType.BLOCKED_UNHEALTHY:
            asyncio.create_task(
                self.notify_boss(
                    decision, tenant,
                    title="⚠️ 账号健康红灯",
                    body=(
                        f"健康分：{decision.health_score:.0f}/100\n"
                        f"已停止自动发送 · 自动切换备用账号（如配置）"
                    ),
                )
            )
            return

        # paused / review_required 不通知 · 老板已知情
        logger.info(
            "auto_send blocked tenant=%s decision=%s reason=%s",
            tenant.tenant_id, decision.decision.value, decision.reason,
        )


_default_decider: Optional[AutoSendDecider] = None


def get_default_decider() -> AutoSendDecider:
    global _default_decider
    if _default_decider is None:
        _default_decider = AutoSendDecider()
    return _default_decider


def reset_default_decider() -> None:
    global _default_decider
    _default_decider = None
