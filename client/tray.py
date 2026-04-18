"""系统托盘模块 · F4。

绿/黄/红三色状态图标 + 暂停/恢复/退出/打开 Dashboard 菜单。
无 pystray 时自动降级为 logger-only 模式（macOS dev / 测试环境）。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger("baiyang.tray")

# 状态 → 颜色 RGB（PIL Image 用）
_STATUS_COLORS: dict[str, tuple[int, int, int]] = {
    "green": (34, 197, 94),
    "yellow": (250, 204, 21),
    "red": (239, 68, 68),
}

_VALID_STATUSES = frozenset(_STATUS_COLORS)


def _make_icon_image(color: tuple[int, int, int]):
    """生成 16x16 纯色圆形图标（需 PIL）。"""
    try:
        from PIL import Image, ImageDraw  # noqa: PLC0415
        img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((1, 1, 14, 14), fill=color + (255,))
        return img
    except ImportError:
        return None


class TrayIcon:
    """系统托盘图标。

    Args:
        on_pause: 点击"暂停"时调用。
        on_resume: 点击"恢复"时调用。
        on_quit: 点击"退出"时调用。
        on_open_dashboard: 点击"打开 Dashboard"时调用。
    """

    def __init__(
        self,
        on_pause: Callable[[], None],
        on_resume: Callable[[], None],
        on_quit: Callable[[], None],
        on_open_dashboard: Callable[[], None],
    ):
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_quit = on_quit
        self._on_open_dashboard = on_open_dashboard
        self.status: str = "green"
        self._icon = None  # pystray.Icon 实例（有 pystray 时填充）

    # ── 状态控制 ──────────────────────────────────────────────────────────

    def set_status(self, status: str) -> None:
        """green / yellow / red · 更新托盘图标颜色。"""
        if status not in _VALID_STATUSES:
            logger.warning("未知状态 '%s'，忽略（有效值：%s）", status, _VALID_STATUSES)
            return
        self.status = status
        logger.info("托盘状态 → %s", status)
        if self._icon is not None:
            try:
                self._icon.icon = _make_icon_image(_STATUS_COLORS[status])
            except Exception as exc:
                logger.debug("更新托盘图标失败: %s", exc)

    # ── 内部菜单动作 ──────────────────────────────────────────────────────

    def _action_pause(self, icon=None, item=None) -> None:
        logger.info("托盘：暂停")
        self._on_pause()
        self.set_status("yellow")

    def _action_resume(self, icon=None, item=None) -> None:
        logger.info("托盘：恢复")
        self._on_resume()
        self.set_status("green")

    def _action_dashboard(self, icon=None, item=None) -> None:
        logger.info("托盘：打开 Dashboard")
        self._on_open_dashboard()

    def _action_quit(self, icon=None, item=None) -> None:
        logger.info("托盘：退出")
        if self._icon is not None:
            self._icon.stop()
        self._on_quit()

    # ── 运行 ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """阻塞运行系统托盘。无 pystray 时降级为日志提示。"""
        try:
            import pystray  # noqa: PLC0415
            from pystray import MenuItem as Item  # noqa: PLC0415

            menu = pystray.Menu(
                Item("打开 Dashboard", self._action_dashboard),
                Item("暂停", self._action_pause),
                Item("恢复", self._action_resume),
                pystray.Menu.SEPARATOR,
                Item("退出", self._action_quit),
            )
            icon_image = _make_icon_image(_STATUS_COLORS[self.status])
            self._icon = pystray.Icon(
                name="WechatAgent",
                icon=icon_image,
                title="WechatAgent",
                menu=menu,
            )
            logger.info("系统托盘已启动（pystray）")
            self._icon.run()
        except ImportError:
            logger.warning(
                "pystray 未安装 · 托盘降级为 logger-only 模式 · "
                "（测试/macOS dev 环境正常）"
            )
            self._run_fallback()

    def _run_fallback(self) -> None:
        """无 pystray 时的 fallback：仅记日志，不阻塞。"""
        logger.info(
            "TrayIcon fallback 模式 · 状态=%s · "
            "回调: pause=%s resume=%s quit=%s dashboard=%s",
            self.status,
            self._on_pause,
            self._on_resume,
            self._on_quit,
            self._on_open_dashboard,
        )

    def stop(self) -> None:
        """从外部停止托盘（测试用）。"""
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
