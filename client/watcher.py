"""WeChatWatcher · 监听微信新消息 · 真模式 wxautox · mock 模式 macOS 跑通。"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

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
        on_suggestion: OnSuggestionCallback | None = None,
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

            # 实例化失败时, 真打印客户机微信版本 + wxauto4 真支持版本
            # wxauto4 v41.1.2 真支持: 微信 4.0.5.13 / 4.0.5.26 (cluic/wxauto4 issue #7 maintainer 真回复)
            import time
            mod_name, desc, WeChatCls = usable[0]
            try:
                self._wx = WeChatCls()
                self._engine_name = mod_name
                logger.info("✅ 微信自动化引擎激活: %s", mod_name)
                print("✅ 微信已连接, 开始监听消息", flush=True)
                return
            except Exception as e:
                err_str = str(e)
                is_no_window = ('未找到' in err_str or '主窗口' in err_str or
                                 '登录' in err_str or 'NotFound' in err_str or
                                 'window' in err_str.lower())
                if is_no_window:
                    # 真根因: wxauto4 hardcoded ClassName 不匹配客户机微信版本
                    # 给客户精准诊断 — 客户机微信版本 + wxauto4 真支持版本
                    try:
                        from client.version_probe import detect_wechat_version
                        wx_ver = detect_wechat_version() or "未探测到"
                    except Exception:
                        wx_ver = "未探测到"
                    # 列出客户机所有微信进程
                    proc_info = ""
                    try:
                        import psutil  # type: ignore
                        wx_procs = []
                        for p in psutil.process_iter(['name', 'exe']):
                            n = (p.info.get('name') or '').lower()
                            if n in ('weixin.exe', 'wechat.exe'):
                                wx_procs.append(f"  - {p.info.get('name')} @ {p.info.get('exe')}")
                        proc_info = "\n".join(wx_procs) if wx_procs else "  (未发现微信进程)"
                    except Exception as pe:
                        proc_info = f"  (psutil 探测失败: {pe})"
                    diag = (
                        f"❌ wxauto4 找不到微信主窗口\n\n"
                        f"客户机微信版本: {wx_ver}\n"
                        f"客户机微信进程:\n{proc_info}\n\n"
                        f"━━━━━━ 真根因 ━━━━━━\n"
                        f"wxauto4 v41.1.2 仅支持微信 4.0.5.13 或 4.0.5.26 这两个特定版本.\n"
                        f"(来源: github.com/cluic/wxauto4 issue #7 maintainer 回复)\n\n"
                        f"━━━━━━ 解决 ━━━━━━\n"
                        f"装微信 4.0.5.26 (wxauto4 真支持):\n"
                        f"  https://github.com/SiverKing/wechat4.0-windows-versions/releases\n\n"
                        f"原始报错: {type(e).__name__}: {e}\n"
                    )
                    logger.error(diag)
                    raise RuntimeError(diag) from e
                # 非主窗口错 (杀毒拦截 / 权限不足)
                logger.error("引擎 %s 真实失败: %s", mod_name, e, exc_info=True)
                raise RuntimeError(
                    f"微信自动化引擎 {mod_name} 启动失败:\n  {type(e).__name__}: {e}\n\n"
                    "常见原因: (1) Windows 杀毒拦截 uiautomation (2) 微信版本不兼容 (3) 权限不足"
                ) from e

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
