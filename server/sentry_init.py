"""server/sentry_init.py · 服务端 Sentry 异常上报。

best-effort：缺 sentry-sdk 或 DSN 未配置不影响正常运行。
在 FastAPI lifespan 最早调用 init_sentry()。
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("baiyang.server.sentry")


def init_sentry(app=None, release: str = "unknown") -> bool:
    """初始化服务端 Sentry SDK。

    Args:
        app:     FastAPI 实例（可选 · 用于 FastAPI integration）
        release: 版本号

    Returns:
        True  成功初始化
        False sentry-sdk 未安装或 DSN 未配置
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        logger.debug("SENTRY_DSN not set · sentry disabled")
        return False

    try:
        import sentry_sdk  # type: ignore
        from sentry_sdk.integrations.logging import LoggingIntegration  # type: ignore
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration  # type: ignore

        integrations = [
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
            SqlalchemyIntegration(),
        ]

        # FastAPI / Starlette integration（可选）
        try:
            from sentry_sdk.integrations.starlette import StarletteIntegration  # type: ignore
            from sentry_sdk.integrations.fastapi import FastApiIntegration  # type: ignore
            integrations += [StarletteIntegration(), FastApiIntegration()]
        except ImportError:
            pass

        sentry_sdk.init(
            dsn=dsn,
            integrations=integrations,
            release=release,
            environment=os.getenv("BAIYANG_ENV", "production"),
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            # 跨租户红线：确保异常上报不含 request body
            before_send=_before_send,
        )
        logger.info("sentry initialized (server) dsn=%s...", dsn[:20])
        return True
    except ImportError:
        logger.debug("sentry-sdk not installed · skipping")
        return False
    except Exception as exc:
        logger.warning("sentry init failed: %s", exc)
        return False


def _before_send(event: dict, hint: dict) -> dict:
    """过滤 request body，防止客户聊天内容泄露到 Sentry。"""
    if "request" in event:
        req = event["request"]
        req.pop("data", None)      # POST body
        req.pop("cookies", None)   # session cookies
    return event


def capture_exception(exc: Exception, tenant_id: str = "") -> None:
    """手动捕获异常（sentry 未初始化时静默）。"""
    try:
        import sentry_sdk  # type: ignore
        with sentry_sdk.push_scope() as scope:
            if tenant_id:
                scope.set_tag("tenant_id", tenant_id)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass
