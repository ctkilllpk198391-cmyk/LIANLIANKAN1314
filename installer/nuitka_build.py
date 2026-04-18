"""Nuitka 编译脚本 · macOS dev 准备 + Windows 真编译。

用法 (Windows):
    python installer/nuitka_build.py --output-dir dist

输出：dist/wechat_agent.exe（standalone）

macOS 注意：Nuitka 在 macOS 上只输出构建命令供参考，
真正编译需在 Windows 机器上执行。
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PRODUCT_NAME = "WechatAgent"
COMPANY_NAME = "wechat_agent"
FILE_VERSION = "0.1.0"
PRODUCT_VERSION = "0.1.0"

NUITKA_FLAGS = [
    "--standalone",
    "--onefile",
    "--windows-disable-console",
    "--include-package=client",
    "--include-package=server",
    "--include-package=shared",
    "--enable-plugin=pyside6",
    f"--company-name={COMPANY_NAME}",
    f"--product-name={PRODUCT_NAME}",
    f"--file-version={FILE_VERSION}",
    f"--product-version={PRODUCT_VERSION}",
]

ENTRY_POINT = "client/main.py"


def build(entry: str = ENTRY_POINT, extra_flags: list[str] | None = None, output_dir: str = "dist") -> int:
    """构建命令，返回 returncode（macOS 上仅打印命令）。"""
    flags = list(NUITKA_FLAGS) + [f"--output-dir={output_dir}"]
    if extra_flags:
        flags.extend(extra_flags)

    cmd = [sys.executable, "-m", "nuitka"] + flags + [entry]

    print("=== Nuitka 编译命令 ===")
    print(" ".join(cmd))
    print("=" * 40)

    if sys.platform == "win32":
        result = subprocess.run(cmd, check=False)
        return result.returncode
    else:
        print("[INFO] 非 Windows 环境 · 仅输出构建命令 · 跳过真实编译")
        print("[INFO] 请在 Windows 机器上运行以上命令完成真实编译")
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nuitka 编译脚本 · 生成 wechat_agent standalone 可执行文件"
    )
    parser.add_argument(
        "--entry",
        default=ENTRY_POINT,
        help=f"入口文件（默认：{ENTRY_POINT}）",
    )
    parser.add_argument(
        "--output-dir",
        default="dist",
        help="输出目录（默认：dist）",
    )
    parser.add_argument(
        "--extra-flag",
        action="append",
        dest="extra_flags",
        default=[],
        help="额外 Nuitka 参数（可重复）",
    )
    args = parser.parse_args()

    rc = build(entry=args.entry, extra_flags=args.extra_flags, output_dir=args.output_dir)
    if rc != 0:
        print(f"[ERROR] Nuitka 编译失败，returncode={rc}", file=sys.stderr)
        sys.exit(rc)
    else:
        print("[OK] 完成")


if __name__ == "__main__":
    main()
