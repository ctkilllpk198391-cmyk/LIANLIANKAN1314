"""客户端主入口 · 串联 watcher → review_popup → sender。

用法:
  python -m client.main --tenant tenant_0001 --server http://127.0.0.1:8327
  python -m client.main --tenant tenant_0001 --mock      # macOS 调试模式
  python -m client.main --diagnose                       # 输出环境诊断报告
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import platform
import sys
import traceback
from datetime import datetime
from pathlib import Path

# === stdout 强制 unbuffered + UTF-8 (Windows cmd + PyInstaller --onefile 防黑屏) ===
try:
    sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')  # type: ignore
    sys.stderr.reconfigure(line_buffering=True, encoding='utf-8')  # type: ignore
except Exception:
    pass

# === 强制文件日志(永远会写,console 黑屏也能看)===
def _setup_log_dir() -> Path:
    """日志目录:Windows 用 LocalAppData,其他平台用 home。"""
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', os.environ.get('TEMP', '.')))
    else:
        base = Path.home()
    log_dir = base / 'WechatAgent' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

LOG_DIR = _setup_log_dir()
LOG_FILE = LOG_DIR / f'client-{datetime.now().strftime("%Y%m%d")}.log'

# 立即往文件写一行,验证可写
try:
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"\n{'=' * 60}\n")
        f.write(f"  wechat_agent client booting at {datetime.now().isoformat()}\n")
        f.write(f"  Python: {sys.version}\n")
        f.write(f"  Platform: {platform.platform()}\n")
        f.write(f"  Args: {sys.argv[1:]}\n")
        f.write(f"  Log file: {LOG_FILE}\n")
        f.write(f"{'=' * 60}\n")
except Exception as e:
    print(f"WARN: cannot write log file {LOG_FILE}: {e}", flush=True)

# Boot banner (console)
print("=" * 60, flush=True)
print("  wechat_agent client booting...", flush=True)
print(f"  Log: {LOG_FILE}", flush=True)
print("  (first launch may take 1-3 min · Windows Defender)", flush=True)
print("=" * 60, flush=True)
print(f"  Python: {sys.version.split()[0]}", flush=True)
print(f"  Args: {' '.join(sys.argv[1:])}", flush=True)
print("=" * 60, flush=True)

from client.api_client import ServerAPIClient
from client.review_popup import ConsoleReviewPopup, HeadlessAutoAccept
from client.risk_control import RiskController, WorkSchedule
from client.sender import HumanLikeSender
from client.version_probe import detect_wechat_version
from client.watcher import WeChatWatcher
from shared.proto import ReviewDecision, SendAck, Suggestion
from shared.types import ReviewDecisionEnum

# 双 handler · console + file 都写
_log_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_log_fmt)
_file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
_file_handler.setFormatter(_log_fmt)
_root_logger = logging.getLogger()
_root_logger.setLevel(logging.INFO)
_root_logger.handlers.clear()
_root_logger.addHandler(_console_handler)
_root_logger.addHandler(_file_handler)
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
    p.add_argument("--tenant", default="tenant_0001", help="tenant_id (如 tenant_0001)")
    p.add_argument("--server", default="http://120.26.208.212", help="server URL")
    p.add_argument("--mock", action="store_true", help="mock 模式 · macOS 调试")
    p.add_argument("--auto-accept", action="store_true", help="无人值守自动 accept (仅测试)")
    p.add_argument("--check-only", action="store_true",
                   help="只跑 server health + 微信版本探测,验证后退出(CI smoke test 用)")
    p.add_argument("--diagnose", action="store_true",
                   help="输出完整环境诊断报告(Windows/微信/wxauto引擎/server/.env),不启动服务")
    return p.parse_args()


def run_diagnose() -> None:
    """完整环境诊断 · 输出 JSON 到 console + log 文件 + 桌面 wxagent_diagnose.json"""
    report: dict = {
        "timestamp": datetime.now().isoformat(),
        "system": {
            "platform": platform.platform(),
            "python": sys.version,
            "executable": sys.executable,
            "frozen": getattr(sys, 'frozen', False),
        },
        "args": sys.argv[1:],
        "log_dir": str(LOG_DIR),
        "log_file": str(LOG_FILE),
        "engines": {},
        "wechat_version": None,
        "server_health": None,
        "env_file": None,
    }
    # 引擎探测
    for name in ['wxautox4', 'wxauto4', 'wxautox', 'wxauto', 'uiautomation', 'win32api', 'humancursor']:
        try:
            mod = __import__(name)
            ver = getattr(mod, '__version__', 'unknown')
            report["engines"][name] = {"installed": True, "version": str(ver)}
        except ImportError as e:
            report["engines"][name] = {"installed": False, "error": str(e)}
        except Exception as e:
            report["engines"][name] = {"installed": "?", "error": f"{type(e).__name__}: {e}"}
    # 微信版本
    try:
        from client.version_probe import detect_wechat_version
        report["wechat_version"] = detect_wechat_version()
    except Exception as e:
        report["wechat_version"] = f"探测失败: {e}"
    # server health
    try:
        import urllib.request
        import urllib.error
        url = "http://120.26.208.212/v1/health"
        with urllib.request.urlopen(url, timeout=10) as r:
            report["server_health"] = json.loads(r.read().decode('utf-8'))
    except Exception as e:
        report["server_health"] = f"server 不可达: {type(e).__name__}: {e}"
    # .env 文件
    env_candidates = [
        Path(sys.executable).parent / '.env',
        LOG_DIR.parent / '.env',
    ]
    for cand in env_candidates:
        if cand.exists():
            try:
                report["env_file"] = {"path": str(cand), "content": cand.read_text(encoding='utf-8')}
            except Exception as e:
                report["env_file"] = {"path": str(cand), "error": str(e)}
            break
    # 输出 (桌面文件由外层 startup/crash hook 唯一负责, 避免一次跑生成多个)
    output = json.dumps(report, ensure_ascii=False, indent=2)
    print(output, flush=True)
    # 写 log
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write("\n=== DIAGNOSE ===\n")
            f.write(output)
            f.write("\n")
    except Exception:
        pass


def main() -> None:
    args = parse_args()

    # --diagnose 模式:输出环境报告后退出
    if args.diagnose:
        run_diagnose()
        return

    if not args.mock and platform.system() != "Windows":
        logger.warning("非 Windows 环境，强制启用 --mock")
        args.mock = True

    # 万能版: 启动立即写诊断到桌面 (即使没 crash, 客户也有完整环境快照)
    try:
        if sys.platform == 'win32':
            _desktop = Path(os.environ.get('USERPROFILE', '.')) / 'Desktop'
        else:
            _desktop = Path.home() / 'Desktop'
        _startup_log = _desktop / f'wxagent_startup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
        # 自动跑 diagnose 收集环境快照
        _orig_stdout = sys.stdout
        import io
        sys.stdout = io.StringIO()
        try:
            run_diagnose()
        except SystemExit:
            pass
        except Exception as _e:
            sys.stdout = _orig_stdout
            print(f"WARN: 自动诊断失败: {_e}", flush=True)
        else:
            _diag_text = sys.stdout.getvalue()
            sys.stdout = _orig_stdout
            try:
                _startup_log.write_text(
                    f"=== wxagent 启动诊断 {datetime.now().isoformat()} ===\n\n{_diag_text}",
                    encoding='utf-8'
                )
                print(f"启动诊断报告: {_startup_log}", flush=True)
            except Exception as _e:
                print(f"WARN: 写桌面诊断失败: {_e}", flush=True)
    except Exception as _e:
        print(f"WARN: 启动诊断异常: {_e}", flush=True)

    # 全局未捕获异常 → 写日志 + 桌面 crash report (含完整 diagnose + traceback + 最近 log)
    def _excepthook(exc_type, exc_value, exc_tb):
        tb = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical("未捕获异常:\n%s", tb)
        try:
            if sys.platform == 'win32':
                desktop = Path(os.environ.get('USERPROFILE', '.')) / 'Desktop'
            else:
                desktop = Path.home() / 'Desktop'
            crash_file = desktop / f'wxagent_crash_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
            # 收集完整诊断 (调 run_diagnose 把环境快照合进 crash report)
            try:
                _orig = sys.stdout
                sys.stdout = io.StringIO()
                run_diagnose()
                _diag = sys.stdout.getvalue()
                sys.stdout = _orig
            except Exception:
                _diag = "(diagnose 失败)"
            # 最近 log 末 100 行
            _recent_log = ""
            try:
                if LOG_FILE.exists():
                    _lines = LOG_FILE.read_text(encoding='utf-8', errors='replace').splitlines()
                    _recent_log = "\n".join(_lines[-100:])
            except Exception:
                _recent_log = "(log 读取失败)"
            crash_file.write_text(
                f"=== wxagent 崩溃报告 {datetime.now().isoformat()} ===\n\n"
                f"### 异常 traceback\n{tb}\n\n"
                f"### 环境诊断快照\n{_diag}\n\n"
                f"### 最近 100 行 log\n{_recent_log}\n",
                encoding='utf-8'
            )
            print(f"\n崩溃报告 (含完整诊断): {crash_file}", flush=True)
            print(f"  把这个文件发给技术团队即可定位问题", flush=True)
        except Exception as _hook_e:
            print(f"\n崩溃但无法写桌面 crash 报告: {_hook_e}", flush=True)
    sys.excepthook = _excepthook

    app = ClientApp(
        server_url=args.server,
        tenant_id=args.tenant,
        mock=args.mock,
        auto_accept=args.auto_accept,
    )

    if args.check_only:
        # CI smoke test: 仅验证 server 可达 + 微信版本探测,不启动 watcher
        async def _check():
            health = await app.api.health()
            if not health:
                logger.error("FAIL: server unreachable: %s", args.server)
                sys.exit(1)
            logger.info("OK: server health = %s", health)
            if not app.mock:
                v = detect_wechat_version()
                logger.info("WeChat PC version: %s (None = not installed, OK for CI)",
                            v or "None")
            logger.info("CHECK-ONLY PASSED")
        asyncio.run(_check())
        return

    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("收到 Ctrl+C · 退出")


if __name__ == "__main__":
    main()
