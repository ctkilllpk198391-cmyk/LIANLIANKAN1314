"""WeChatWatcher · 监听微信新消息 · 真模式 wxautox · mock 模式 macOS 跑通。"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable, Optional

from client.api_client import ServerAPIClient
from shared.proto import InboundMsg, Suggestion

logger = logging.getLogger(__name__)


OnSuggestionCallback = Callable[[Suggestion], Awaitable[None]]


class WeChatWatcher:
    def __init__(
        self,
        server_url: str,
        tenant_id: str,
        mock: bool = False,
        on_suggestion: Optional[OnSuggestionCallback] = None,
    ):
        self.tenant_id = tenant_id
        self.mock = mock
        self.api = ServerAPIClient(server_url)
        self.on_suggestion = on_suggestion
        self._wx = None  # 真模式才注入
        self._running = False

    def _ensure_wx(self) -> None:
        if self.mock:
            return
        if self._wx is None:
            engines = [
                ('wxauto4',  '开源 · 微信 4.x'),
            ]
            # 先做 import 测试: import 失败 = 真 deps 缺, 直接 raise (不可恢复)
            import_errors = []
            usable = []
            for mod_name, desc in engines:
                try:
                    mod = __import__(mod_name)
                    WeChatCls = getattr(mod, 'WeChat', None)
                    if WeChatCls is None:
                        import_errors.append(f"{mod_name}: 模块没 WeChat 类")
                        continue
                    usable.append((mod_name, desc, WeChatCls))
                except ImportError as e:
                    import_errors.append(f"{mod_name} ImportError: {e}")
            if not usable:
                raise RuntimeError(
                    "微信自动化引擎依赖缺失:\n  " + "\n  ".join(import_errors) +
                    "\n\n这是打包问题, 请反馈技术团队. 桌面 wxagent_*.txt 已写诊断报告."
                )

            # 实例化: 失败如果是"主窗口未找到/未登录" → 轮询等微信打开 (用户友好)
            # 不是 traceback 闪退
            import time
            mod_name, desc, WeChatCls = usable[0]
            print("=" * 60, flush=True)
            print("⚠️  请确保微信 PC 客户端已打开并登录", flush=True)
            print("    程序将等待微信启动 (最多 5 分钟)...", flush=True)
            print("=" * 60, flush=True)
            logger.info("尝试引擎: %s (%s) · 等待微信主窗口", mod_name, desc)
            max_retries = 60  # 60 * 5s = 5 min
            last_err = None
            for i in range(max_retries):
                try:
                    self._wx = WeChatCls()
                    self._engine_name = mod_name
                    logger.info("✅ 微信自动化引擎激活: %s (尝试 %d 次)", mod_name, i + 1)
                    print(f"✅ 微信已连接, 开始监听消息", flush=True)
                    return
                except Exception as e:
                    last_err = e
                    err_str = str(e)
                    is_no_window = ('未找到' in err_str or '主窗口' in err_str or
                                     '登录' in err_str or 'NotFound' in err_str or
                                     'window' in err_str.lower())
                    if is_no_window and i < max_retries - 1:
                        if i % 6 == 0:  # 每 30s 提示一次
                            print(f"等待微信主窗口... ({i*5}s/{max_retries*5}s) — 请打开微信 PC 客户端并登录", flush=True)
                        time.sleep(5)
                        continue
                    if not is_no_window:
                        # 非主窗口类错误 (如杀毒拦截), 直接 raise
                        logger.error("引擎 %s 真实失败: %s", mod_name, e, exc_info=True)
                        raise RuntimeError(
                            f"微信自动化引擎 {mod_name} 启动失败:\n  {type(e).__name__}: {e}\n\n"
                            "常见原因: (1) Windows 杀毒拦截 uiautomation (2) 微信版本 < 4.x (3) 权限不足"
                        ) from e
                    time.sleep(5)
            # 5 min 超时
            raise RuntimeError(
                f"等待微信主窗口超时 (5 分钟):\n  {last_err}\n\n"
                "请: (1) 启动微信 PC 客户端 (2) 完成登录 (3) 重新启动本程序"
            )

    async def start(self) -> None:
        self._ensure_wx()
        self._running = True
        if self.mock:
            logger.info("mock 模式启动 · 不实际监听微信")
            return

        loop = asyncio.get_event_loop()
        while self._running:
            try:
                msgs = await loop.run_in_executor(None, self._wx.GetAllNewMessage)
                for chat_name, message_list in (msgs or {}).items():
                    for m in message_list:
                        await self._handle_raw(chat_name, m)
            except Exception as e:
                logger.exception("watcher loop error: %s", e)
            await asyncio.sleep(1.0)

    def stop(self) -> None:
        self._running = False

    async def _handle_raw(self, chat_name: str, raw_msg) -> None:
        # raw_msg 结构来自 wxauto · 字段名以 wxauto 4.x 为准
        # 这里抽象为 InboundMsg
        text = getattr(raw_msg, "content", "") or str(raw_msg)
        sender = getattr(raw_msg, "sender", chat_name)
        if not text.strip():
            return

        msg = InboundMsg(
            tenant_id=self.tenant_id,
            chat_id=chat_name,
            sender_id=sender,
            sender_name=sender,
            text=text,
            timestamp=int(time.time()),
        )
        await self.submit(msg)

    async def submit(self, msg: InboundMsg) -> Suggestion:
        suggestion = await self.api.submit_inbound(msg)
        if self.on_suggestion:
            await self.on_suggestion(suggestion)
        return suggestion
