"""F1 兜底 · 老板手机通知 · 飞书 webhook（mock 默认）。

使用：
  notifier = BossNotifier()
  await notifier.notify(tenant_id, title="高风险消息熔断", body="...")

环境变量：
  BAIYANG_FEISHU_WEBHOOK   不设 → 仅 logger.warning · 不真发
  BAIYANG_NOTIFIER_MOCK    true → 强制 mock 即使有 webhook（测试用）

每个 tenant 也可以在 TenantConfig 里配 `boss_phone_webhook` 覆盖全局。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class BossNotifier:
    def __init__(self, default_webhook: Optional[str] = None, mock: Optional[bool] = None):
        self.default_webhook = default_webhook or os.getenv("BAIYANG_FEISHU_WEBHOOK")
        if mock is None:
            mock = os.getenv("BAIYANG_NOTIFIER_MOCK", "false").lower() == "true"
        self.mock = mock
        self._sent_log: list[dict] = []   # 测试用 · 内存留痕

    async def notify(
        self,
        tenant_id: str,
        title: str,
        body: str,
        webhook: Optional[str] = None,
    ) -> bool:
        """发送通知。返回 True=成功 · False=失败/mock。"""
        target = webhook or self.default_webhook
        record = {"tenant_id": tenant_id, "title": title, "body": body, "webhook": target}
        self._sent_log.append(record)

        if self.mock or not target:
            logger.warning("[notifier MOCK] tenant=%s · %s · %s", tenant_id, title, body)
            return False

        payload = {
            "msg_type": "text",
            "content": {"text": f"【{title}】\n{body}\n(tenant: {tenant_id})"},
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
                async with s.post(target, json=payload) as r:
                    if r.status >= 400:
                        logger.error("notifier %s failed: %d", target, r.status)
                        return False
            return True
        except Exception as e:
            logger.error("notifier %s exception: %s", target, e)
            return False

    @property
    def sent_count(self) -> int:
        return len(self._sent_log)

    def get_log(self) -> list[dict]:
        return list(self._sent_log)


_default_notifier: Optional[BossNotifier] = None


def get_default_notifier() -> BossNotifier:
    global _default_notifier
    if _default_notifier is None:
        _default_notifier = BossNotifier()
    return _default_notifier


def reset_default_notifier() -> None:
    global _default_notifier
    _default_notifier = None
