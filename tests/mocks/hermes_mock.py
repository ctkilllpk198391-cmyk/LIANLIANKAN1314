"""mock hermes 响应工厂。"""

from __future__ import annotations


def make_hermes_text(prompt: str, model_route: str = "hermes_default") -> str:
    return f"[mock·{model_route}] 已收到，给您建议：稍等我看看～"


def make_high_risk_response() -> str:
    """触发禁用词的响应，用于测试 generator 重写逻辑。"""
    return "我保证一定给您终身免单！"  # 命中"保证/一定/终身"
