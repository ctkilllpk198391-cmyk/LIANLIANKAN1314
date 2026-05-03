"""V11 客户机入口 — chisel client (反向 SOCKS5 出口) + 扫码 UI.

替代 V2-V10 wxauto4 路线. 客户机不再装微信自动化, 只做 IP 出口 + 扫码.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.request import urlopen

import requests

logger = logging.getLogger(__name__)

# ECS 公网 IP — 启动时从环境拿, 默认 8.153.106.103 (lian 阿里云)
ECS_HOST = os.environ.get("WECHAT_AGENT_ECS", "8.153.106.103")
CHISEL_PORT = int(os.environ.get("CHISEL_PORT", "7000"))
CHISEL_AUTH = os.environ.get("CHISEL_AUTH", "wechat:agent2026")
SERVER_URL = os.environ.get("SERVER_URL", f"http://{ECS_HOST}")
TENANT_ID = os.environ.get("TENANT_ID", "tenant_0001")


def get_chisel_binary() -> Path:
    """返回打包内 chisel 二进制路径 (PyInstaller 打包时嵌入)."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        base = Path(sys._MEIPASS)  # type: ignore
    else:
        base = Path(__file__).parent.parent / "vendor"

    if platform.system() == "Windows":
        return base / "chisel.exe"
    return base / "chisel"


def start_chisel_reverse(stop_event: threading.Event) -> None:
    """启动 chisel client 走客户机 IP 出口的反向 SOCKS5 通道.

    ECS 上 chisel server :7000, 客户机连过去 + 反向暴露 :1080 SOCKS5.
    WeChatPadPro Docker 配置走 ECS:1080 即经客户机出口.
    """
    chisel = get_chisel_binary()
    if not chisel.exists():
        logger.error("chisel binary 不存在: %s", chisel)
        return

    cmd = [
        str(chisel),
        "client",
        "--auth", CHISEL_AUTH,
        f"{ECS_HOST}:{CHISEL_PORT}",
        "R:1080:socks",  # ECS 上 :1080 → 客户机 SOCKS5 出口
    ]
    logger.info("启动 chisel: %s", " ".join(cmd))

    while not stop_event.is_set():
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            while proc.poll() is None and not stop_event.is_set():
                time.sleep(2)
            if proc.poll() is None:
                proc.terminate()
            else:
                logger.warning("chisel 退出 code=%s, 5s 后重连", proc.returncode)
        except Exception as e:
            logger.exception("chisel 异常: %s", e)
        if not stop_event.is_set():
            time.sleep(5)


def fetch_qr_url() -> str:
    """从 server 拿 WeChatPadPro 扫码 URL."""
    r = requests.post(
        f"{SERVER_URL}/api/wechatpad/get_qr",
        json={"tenant_id": TENANT_ID},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return data["qr_url"]


def show_qr_window(qr_url: str, stop_event: threading.Event) -> None:
    """tkinter 弹窗显示扫码 + 状态."""
    root = tk.Tk()
    root.title("微信助手 · 扫码登录")
    root.geometry("400x500")

    tk.Label(root, text="请用手机微信扫码登录", font=("微软雅黑", 14)).pack(pady=10)

    # QR 图通过 server 获取或浏览器打开 URL
    tk.Label(
        root,
        text=f"扫码地址:\n{qr_url}\n\n(复制到微信扫一扫)",
        wraplength=380,
        justify="left",
    ).pack(pady=20)

    status_var = tk.StringVar(value="等待扫码...")
    tk.Label(root, textvariable=status_var, fg="blue").pack(pady=10)

    def poll_login():
        while not stop_event.is_set():
            try:
                r = requests.post(
                    f"{SERVER_URL}/api/wechatpad/check_login",
                    json={"tenant_id": TENANT_ID},
                    timeout=10,
                )
                d = r.json()
                if d.get("logged_in"):
                    status_var.set("✅ 登录成功! 服务已激活")
                    time.sleep(2)
                    root.quit()
                    return
                else:
                    status_var.set(f"等待中... ({d.get('status', '?')})")
            except Exception as e:
                status_var.set(f"网络错误: {e}")
            time.sleep(3)

    threading.Thread(target=poll_login, daemon=True).start()
    root.mainloop()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger.info("V11 客户机启动 · ECS=%s · tenant=%s", ECS_HOST, TENANT_ID)

    stop_event = threading.Event()

    # 后台启 chisel
    chisel_thread = threading.Thread(target=start_chisel_reverse, args=(stop_event,), daemon=True)
    chisel_thread.start()

    # 等 chisel 连上 (3s)
    time.sleep(3)

    # 拿扫码 URL + 显示
    try:
        qr_url = fetch_qr_url()
        show_qr_window(qr_url, stop_event)
    except Exception as e:
        logger.exception("扫码失败: %s", e)
        # 桌面写错误日志
        if platform.system() == "Windows":
            desktop = Path(os.environ.get("USERPROFILE", ".")) / "Desktop"
        else:
            desktop = Path.home() / "Desktop"
        err = desktop / f"wxagent_v11_error_{int(time.time())}.txt"
        err.write_text(
            f"V11 启动失败\n\n服务器: {SERVER_URL}\n错误: {e}\n\n"
            f"请检查: 1. 网络通否 2. ECS 是否启动 3. WeChatPadPro Docker 是否跑\n",
            encoding="utf-8",
        )
        print(f"错误日志: {err}", flush=True)

    stop_event.set()
    chisel_thread.join(timeout=5)


if __name__ == "__main__":
    main()
