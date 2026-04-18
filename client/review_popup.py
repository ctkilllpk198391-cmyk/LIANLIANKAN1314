"""审核浮窗 · F1 全自动模式默认不弹 · 仅在 high_risk 或 manual 模式弹。

C4 改动（2026-04-16 First Wave）：
  - 默认 mode='auto' · 全自动模式 · 直接 accept 不交互
  - mode='high_risk_only' · 仅 risk=high 时弹
  - mode='manual' · 所有 suggestion 都弹

兼容保留：
  - ConsoleReviewPopup（manual 模式用）
  - HeadlessAutoAccept（兼容老测试）
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Awaitable, Callable, Optional

from shared.proto import ReviewDecision, Suggestion
from shared.types import ReviewDecisionEnum, RiskEnum

logger = logging.getLogger(__name__)


SubmitDecisionFn = Callable[[ReviewDecision], Awaitable[dict]]


class ReviewMode(str, Enum):
    AUTO = "auto"                       # 全自动 · 不弹 · 默认
    HIGH_RISK_ONLY = "high_risk_only"   # 仅高风险弹
    MANUAL = "manual"                   # 全部弹


def should_popup(suggestion: Suggestion, mode: ReviewMode) -> bool:
    if mode == ReviewMode.AUTO:
        return False
    if mode == ReviewMode.HIGH_RISK_ONLY:
        return suggestion.intent.risk == RiskEnum.HIGH
    return True   # MANUAL


class SmartReviewPopup:
    """根据 mode 决定弹不弹 · 默认 auto 不弹。"""

    def __init__(
        self,
        submit_fn: SubmitDecisionFn,
        mode: ReviewMode = ReviewMode.AUTO,
    ):
        self.submit_fn = submit_fn
        self.mode = mode
        self._console = ConsoleReviewPopup(submit_fn)

    async def show(self, suggestion: Suggestion) -> ReviewDecision:
        if not should_popup(suggestion, self.mode):
            decision = ReviewDecision(
                msg_id=suggestion.msg_id,
                decision=ReviewDecisionEnum.ACCEPT,
                reviewed_at=int(time.time()),
            )
            await self.submit_fn(decision)
            logger.debug("auto-accepted msg=%s mode=%s risk=%s",
                         suggestion.msg_id, self.mode.value, suggestion.intent.risk.value)
            return decision
        return await self._console.show(suggestion)


class ConsoleReviewPopup:
    """控制台手动审核 · MANUAL 模式或 HIGH_RISK 兜底用。"""

    def __init__(self, submit_fn: SubmitDecisionFn):
        self.submit_fn = submit_fn

    async def show(self, suggestion: Suggestion) -> ReviewDecision:
        print("─" * 60)
        print(f"📨 客户消息 → AI 建议（msg_id={suggestion.msg_id}）")
        print(f"  意图: {suggestion.intent.intent.value}（风险: {suggestion.intent.risk.value}）")
        print(f"  路由: {suggestion.model_route} · 重写: {suggestion.rewrite_count}")
        print(f"  建议: {suggestion.text}")
        print("─" * 60)
        print("[a]ccept  [e]dit  [r]eject  → 输入选择：", end="", flush=True)

        loop = asyncio.get_event_loop()
        choice = (await loop.run_in_executor(None, input)).strip().lower()

        if choice == "e":
            print("输入修改后的文本：", end="", flush=True)
            edited = await loop.run_in_executor(None, input)
            decision = ReviewDecision(
                msg_id=suggestion.msg_id,
                decision=ReviewDecisionEnum.EDIT,
                edited_text=edited.strip(),
                reviewed_at=int(time.time()),
            )
        elif choice == "r":
            decision = ReviewDecision(
                msg_id=suggestion.msg_id,
                decision=ReviewDecisionEnum.REJECT,
                reviewed_at=int(time.time()),
            )
        else:
            decision = ReviewDecision(
                msg_id=suggestion.msg_id,
                decision=ReviewDecisionEnum.ACCEPT,
                reviewed_at=int(time.time()),
            )

        await self.submit_fn(decision)
        return decision


class HeadlessAutoAccept:
    """测试用 · 无人值守自动 accept · 等价于 SmartReviewPopup(mode=AUTO)。"""

    def __init__(self, submit_fn: SubmitDecisionFn):
        self.submit_fn = submit_fn

    async def show(self, suggestion: Suggestion) -> ReviewDecision:
        decision = ReviewDecision(
            msg_id=suggestion.msg_id,
            decision=ReviewDecisionEnum.ACCEPT,
            reviewed_at=int(time.time()),
        )
        await self.submit_fn(decision)
        return decision
