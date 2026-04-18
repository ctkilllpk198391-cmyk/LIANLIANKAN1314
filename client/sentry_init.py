"""client/sentry_init.py · 客户端 Sentry 崩溃捕获。

best-effort：缺 sentry-sdk 不影响正常运行。
DSN 走环境变量 SENTRY_DSN。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("baiyang.client.sentry")


def init_sentry(release: str = "unknown") -> bool:
    """初始化客户端 Sentry SDK。

    Returns:
        True  成功初始化
        False sentry-sdk 未安装或 DSN 未配置（不影响运行）
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.debug("SENTRY_DSN not set · sentry disabled")
        return False

    try:
        import sentry_sdk  # type: ignore

        sentry_sdk.init(
            dsn=dsn,
            release=release,
            environment=os.getenv("BAIYANG_ENV", "production"),
            # 采样率：1.0 = 全量，生产可调低
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.2")),
            # 附加用户信息（仅 tenant_id · 不含明文聊天内容）
            before_send=_before_send,
        )
        logger.info("sentry initialized (client) dsn=%s...", dsn[:20])
        return True
    except ImportError:
        logger.debug("sentry-sdk not installed · skipping")
        return False
    except Exception as exc:
        logger.warning("sentry init failed: %s", exc)
        return False


def _before_send(event: dict, hint: dict) -> dict:
    """过滤敏感字段，确保不上传聊天文本。"""
    # 移除 request body（可能含客户聊天内容）
    event.pop("request", None)
    return event


def set_user(tenant_id: str) -> None:
    """设置当前用户上下文（仅 tenant_id）。"""
    try:
        import sentry_sdk  # type: ignore
        sentry_sdk.set_user({"id": tenant_id})
    except Exception:
        pass


def capture_exception(exc: Exception) -> None:
    """手动捕获异常上报（sentry 未初始化时静默）。"""
    try:
        import sentry_sdk  # type: ignore
        sentry_sdk.capture_exception(exc)
    except Exception:
        pass
