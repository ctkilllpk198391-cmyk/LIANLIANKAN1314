"""T5 · 首次安装授权页 · 终端 console 版。"""

from __future__ import annotations

import os
from pathlib import Path

# 默认协议路径
_DEFAULT_LEGAL_PATH = Path(__file__).resolve().parent.parent / "legal" / "data_ownership.md"

# 摘要内容（legal_path 读不到时的兜底）
_FALLBACK_SUMMARY = """
╔══════════════════════════════════════════════════════════════╗
║             wechat_agent · 数据使用授权（必读）              ║
╚══════════════════════════════════════════════════════════════╝

【你的权利】
  ✅ 原始聊天记录归你所有，随时可申请导出（CSV / JSON）
  ✅ 申请删除后 30 天内可撤销，宽限期满后永久删除

【平台所有】
  ❌ AI 学会的回复风格（LoRA 权重）不退还——这是服务核心
  ❌ 客户档案聚合结果 / Embedding 向量属于 wechat_agent 训练资产

【隐私保护】
  🔒 你的数据只服务你，严格 tenant 隔离，不跨客户共享
  🔒 行业聚合分析经差分隐私处理，不可逆追溯个人

完整条款见：legal/data_ownership.md
"""

# 附录章节标题（从 md 中提取摘要用）
_SUMMARY_ANCHOR = "## 附录"


def _read_summary(legal_path: Path) -> str:
    """从 data_ownership.md 读取附录快速摘要章节。"""
    try:
        content = legal_path.read_text(encoding="utf-8")
        idx = content.find(_SUMMARY_ANCHOR)
        if idx == -1:
            return _FALLBACK_SUMMARY
        excerpt = content[idx:idx + 800].strip()
        return f"\n{'='*64}\n  wechat_agent · 数据使用授权（必读）\n{'='*64}\n\n{excerpt}\n"
    except OSError:
        return _FALLBACK_SUMMARY


def show_consent_dialog(legal_path: str | None = None) -> bool:
    """终端打印数据条款摘要，等用户输入 'agree' 同意。

    legal_path 默认 legal/data_ownership.md。
    返回 True 表示用户同意，False 表示拒绝/取消。
    """
    path = Path(legal_path) if legal_path else _DEFAULT_LEGAL_PATH
    summary = _read_summary(path)

    print(summary)
    print("-" * 64)
    print("继续使用 wechat_agent 即代表你已阅读并同意以上条款。")
    print("输入 'agree' 同意并继续，其他任意键退出。")
    print("-" * 64)

    try:
        user_input = input(">>> ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        return False

    agreed = user_input == "agree"
    if agreed:
        print("✅ 已同意数据使用条款，正在启动 wechat_agent...\n")
    else:
        print("❌ 未同意条款，退出。")
    return agreed


if __name__ == "__main__":
    result = show_consent_dialog()
    raise SystemExit(0 if result else 1)
