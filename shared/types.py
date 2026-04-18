"""类型枚举 · Intent / Risk / Plan / ReviewDecision。"""

from __future__ import annotations

from enum import Enum


class IntentEnum(str, Enum):
    GREETING = "greeting"
    INQUIRY = "inquiry"
    NEGOTIATION = "negotiation"
    ORDER = "order"
    COMPLAINT = "complaint"
    CHITCHAT = "chitchat"
    SENSITIVE = "sensitive"
    UNKNOWN = "unknown"


class RiskEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanEnum(str, Enum):
    TRIAL = "trial"
    PRO = "pro"
    FLAGSHIP = "flagship"


class ReviewDecisionEnum(str, Enum):
    ACCEPT = "accept"
    EDIT = "edit"
    REJECT = "reject"


class EmotionEnum(str, Enum):
    """客户情绪 · 与 IntentEnum 正交 · 影响 prompt 调语气策略。"""

    CALM = "calm"          # 平静 · 默认
    ANXIOUS = "anxious"    # 急 · 反复问 · 简短直接
    ANGRY = "angry"        # 不爽 · 投诉 · 共情软化
    EXCITED = "excited"    # 兴奋 · 临门成交信号 · 推优惠
