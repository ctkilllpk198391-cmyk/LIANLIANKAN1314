"""L3 · 微信举报检测 · 监听微信窗口 toast / 警告 · 立即停发 + 推老板。

实现：
  - wxauto 轮询微信主窗口 + 各对话窗口的标题/弹窗文本
  - 命中关键词 → 触发 emergency_stop
  - mock 模式（macOS dev）：用 simulate_alert() 测试

集成点：
  - client/main.py 启动时挂监听
  - 命中 → POST /v1/control/{tenant}/emergency_stop
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# ─── 微信警告/限制关键词 ──────────────────────────────────────────────────

WECHAT_ALERT_PATTERNS = [
    r"被举报",
    r"违规",
    r"限制(发送|登录|功能|使用)",
    r"封禁",
    r"封号",
    r"账号异常",
    r"涉嫌违规",
    r"操作过于频繁",
    r"功能受限",
    r"暂时无法",
    r"异常登录",
    r"安全验证",
]

_ALERT_REGEX = [re.compile(p) for p in WECHAT_ALERT_PATTERNS]


@dataclass
class WeChatAlert:
    matched_text: str
    matched_pattern: str
    detected_at: int


def detect_alert(text: str) -> Optional[WeChatAlert]:
    """文本检测 · 返回首个命中。"""
    if not text or not text.strip():
        return None
    import time
    for pattern in _ALERT_REGEX:
        m = pattern.search(text)
        if m:
            return WeChatAlert(
                matched_text=m.group(0),
                matched_pattern=pattern.pattern,
                detected_at=int(time.time()),
            )
    return None


# ─── 检测器（轮询微信窗口）─────────────────────────────────────────────

EmergencyCallback = Callable[[WeChatAlert], Awaitable[None]]


class WeChatAlertDetector:
    """轮询 wxauto 监听微信主窗口 + 弹窗文本 · 命中 → 调 callback。"""

    POLL_INTERVAL_SEC = 5

    def __init__(
        self,
        on_alert: EmergencyCallback,
        wxauto_provider=None,    # mock 友好 · None 时用 mock
        poll_interval: int = POLL_INTERVAL_SEC,
    ):
        self.on_alert = on_alert
        self.wxauto = wxauto_provider
        self.poll_interval = poll_interval
        self._stop = False
        self._task: Optional[asyncio.Task] = None

    def start(self):
        try:
            loop = asyncio.get_event_loop()
            self._task = loop.create_task(self._run())
        except RuntimeError:
            logger.warning("no event loop · alert detector not started")

    def stop(self):
        self._stop = True
        if self._task and not self._task.done():
            self._task.cancel()

    async def _run(self):
        while not self._stop:
            try:
                texts = self._poll_wechat_texts()
                for text in texts:
                    alert = detect_alert(text)
                    if alert:
                        logger.warning("wechat alert detected: %s", alert.matched_text)
                        await self.on_alert(alert)
                        break   # 已触发 · 不重复（避免一次扫描多次推送）
            except Exception as e:
                logger.error("alert detector poll error: %s", e)
            await asyncio.sleep(self.poll_interval)

    def _poll_wechat_texts(self) -> list[str]:
        """从 wxauto 拉取微信主窗口标题 + 当前弹窗文本。

        mock 模式下返回 _mock_texts 内容（测试用）。"""
        if self.wxauto is None:
            return getattr(self, "_mock_texts", [])
        try:
            return self.wxauto.get_window_texts()
        except Exception as e:
            logger.warning("wxauto poll failed: %s", e)
            return []

    def simulate_alert(self, text: str):
        """测试用：注入伪文本下次轮询命中。"""
        self._mock_texts = [text]


# ─── 集成 helper ─────────────────────────────────────────────────────────

async def emergency_stop_via_api(api_client, tenant_id: str, alert: WeChatAlert) -> bool:
    """触发服务端紧急停止 · 推老板。"""
    if api_client is None:
        logger.warning("[emergency_stop MOCK] tenant=%s alert=%s", tenant_id, alert.matched_text)
        return False
    try:
        await api_client.post_async(
            f"/v1/control/{tenant_id}/emergency_stop",
            json={
                "alert_text": alert.matched_text,
                "pattern": alert.matched_pattern,
                "detected_at": alert.detected_at,
            },
        )
        return True
    except Exception as e:
        logger.error("emergency_stop API failed: %s", e)
        return False
