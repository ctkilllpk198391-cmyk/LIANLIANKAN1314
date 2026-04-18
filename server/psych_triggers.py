"""S2 · 心理学触发器引擎 · Cialdini 6 原则按场景自动选。

第一性原理：销售本质是 6 类触发器的精准投放。
研究证实：损失厌恶（loss aversion）比收益强 2.5 倍。

输入：intent + emotion + customer_profile + 对话阶段
输出：推荐触发器（≤2 个）+ 话术指令（拼进 prompt）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from shared.types import EmotionEnum, IntentEnum


class TriggerType(str, Enum):
    SCARCITY = "scarcity"             # 稀缺：限量/限时
    SOCIAL_PROOF = "social_proof"     # 社会认同：从众
    RECIPROCITY = "reciprocity"       # 互惠：先给价值
    LOSS_AVERSION = "loss_aversion"   # 损失厌恶：不买的代价
    AUTHORITY = "authority"           # 权威：背书
    COMMITMENT = "commitment"         # 承诺一致：复购


class CustomerStage(str, Enum):
    EXPLORE = "explore"        # 初步探索 · 还没明确需求
    COMPARE = "compare"        # 比较中 · 询价砍价
    NEAR = "near"              # 临门一脚 · 即将成交
    POST_BUY = "post_buy"      # 售后 · 已购买
    DORMANT = "dormant"        # 沉睡 · 长期未联系


# 4 维决策矩阵（intent, emotion, stage） → preferred_triggers (top 2)
DECISION_MATRIX: dict[tuple[str, str, str], list[TriggerType]] = {
    # 探索阶段 · 给信任 + 信息
    ("inquiry",     "calm",     "explore"): [TriggerType.RECIPROCITY, TriggerType.AUTHORITY],
    ("inquiry",     "anxious",  "explore"): [TriggerType.AUTHORITY,   TriggerType.SOCIAL_PROOF],
    ("greeting",    "calm",     "explore"): [TriggerType.RECIPROCITY],
    ("chitchat",    "calm",     "explore"): [TriggerType.RECIPROCITY],

    # 比较阶段 · 给从众 + 权威
    ("inquiry",     "calm",     "compare"): [TriggerType.SOCIAL_PROOF, TriggerType.AUTHORITY],
    ("negotiation", "calm",     "compare"): [TriggerType.SOCIAL_PROOF, TriggerType.AUTHORITY],
    ("negotiation", "anxious",  "compare"): [TriggerType.SOCIAL_PROOF, TriggerType.SCARCITY],

    # 临门阶段 · 给稀缺 + 损失厌恶（最强 · +25% 成交）
    ("negotiation", "excited",  "near"):    [TriggerType.SCARCITY,     TriggerType.LOSS_AVERSION],
    ("inquiry",     "excited",  "near"):    [TriggerType.SCARCITY,     TriggerType.LOSS_AVERSION],
    ("order",       "excited",  "near"):    [TriggerType.SCARCITY],
    ("order",       "calm",     "near"):    [TriggerType.LOSS_AVERSION],

    # 售后阶段 · 给承诺 + 互惠
    ("chitchat",    "calm",     "post_buy"): [TriggerType.COMMITMENT,  TriggerType.RECIPROCITY],
    ("inquiry",     "calm",     "post_buy"): [TriggerType.COMMITMENT,  TriggerType.SOCIAL_PROOF],

    # 沉睡客户唤醒 · 互惠 + 稀缺
    ("greeting",    "calm",     "dormant"):  [TriggerType.RECIPROCITY, TriggerType.SCARCITY],
    ("inquiry",     "calm",     "dormant"):  [TriggerType.RECIPROCITY, TriggerType.SOCIAL_PROOF],

    # 投诉/愤怒 · 不推销 · 仅互惠（先解决）
    ("complaint",   "angry",    "explore"):  [TriggerType.RECIPROCITY],
    ("complaint",   "angry",    "compare"):  [TriggerType.RECIPROCITY],
    ("complaint",   "angry",    "near"):     [TriggerType.RECIPROCITY],
    ("complaint",   "angry",    "post_buy"): [TriggerType.RECIPROCITY],
}


# 触发器对应的话术指令（拼进 system prompt）
TRIGGER_INSTRUCTIONS: dict[TriggerType, str] = {
    TriggerType.SCARCITY: (
        "策略：稀缺感 (scarcity)。\n"
        "- 给具体数字：'今天最后 3 件' / '剩 5 个名额'（不要'很少了'）\n"
        "- 给截止时间：'今晚 12 点截止' / '明天涨价'（不要'快了'）\n"
        "- 感叹号 ≤2 个 · 不滥用"
    ),
    TriggerType.SOCIAL_PROOF: (
        "策略：社会认同 (social_proof)。\n"
        "- 用从众语言：'今天 30+ 姐妹下了单' / '上周回购率 80%'\n"
        "- 暗示客户晒单/反馈：'看 → 这是昨天客户的反馈'\n"
        "- 别杜撰数字 · 用大致区间（'30+' 而非'31'）"
    ),
    TriggerType.RECIPROCITY: (
        "策略：互惠 (reciprocity) · 先给价值。\n"
        "- 不直接推销 · 先送资料/对比/小样\n"
        "- 用句式：'我先发对比图给你看 · 不强求买~'\n"
        "- 让客户感觉欠你一份人情 · 后续更愿付款"
    ),
    TriggerType.LOSS_AVERSION: (
        "策略：损失厌恶 (loss_aversion) · 最强触发器（×2.5 收益）。\n"
        "- 把'省 X'改成'不买等于多花 X'\n"
        "- 强调"
        "错过损失：'今天不下等于多花 ¥100 · 因为明早恢复原价'\n"
        "- 用'失去'语气 · 不用'获得'语气"
    ),
    TriggerType.AUTHORITY: (
        "策略：权威 (authority)。\n"
        "- 提资质：'我们这款拿了 XX 认证'\n"
        "- 提专业：'按肤质分 · 你这款是干敏皮'\n"
        "- 提背书：'XX 协会推荐' / 'XX 媒体测评'\n"
        "- 不要说'最好' · 用'专业推荐'"
    ),
    TriggerType.COMMITMENT: (
        "策略：承诺一致 (commitment) · 用于老客户/复购。\n"
        "- 引用过往：'上次你说 X 用得不错 · 这次还要老配方对吗？'\n"
        "- 让客户做小承诺：'要不要先发个 30 ml 体验装试试？'\n"
        "- 顺势升级到正装"
    ),
}


@dataclass
class TriggerRecommendation:
    triggers: list[TriggerType]
    stage: CustomerStage
    instructions: str    # 拼进 prompt 的 psych_block


def detect_stage(
    last_intent: Optional[str],
    last_intents_history: Optional[list[str]] = None,
    has_purchase_history: bool = False,
    days_since_last_message: Optional[int] = None,
    days_since_last_purchase: Optional[int] = None,
) -> CustomerStage:
    """根据客户档案推断当前对话阶段。"""
    history = list(last_intents_history or [])
    if last_intent:
        history.append(last_intent)

    # 沉睡：超 30 天没联系
    if days_since_last_message is not None and days_since_last_message >= 30:
        return CustomerStage.DORMANT

    # 售后：有购买历史 + 当前不在询价/砍价
    if has_purchase_history and last_intent not in ("inquiry", "negotiation", "order"):
        return CustomerStage.POST_BUY

    # 临门：order intent · 或 negotiation 出现 ≥2 次（持续砍价 = 接近成交）
    if last_intent == "order":
        return CustomerStage.NEAR
    neg_count = history.count("negotiation")
    if neg_count >= 2:
        return CustomerStage.NEAR

    # 比较：单次 negotiation 或多次 inquiry
    if last_intent == "negotiation":
        return CustomerStage.COMPARE
    if history.count("inquiry") >= 2:
        return CustomerStage.COMPARE

    # 默认探索
    return CustomerStage.EXPLORE


def recommend_triggers(
    intent: IntentEnum,
    emotion: EmotionEnum,
    stage: CustomerStage,
) -> list[TriggerType]:
    """查决策表 · fallback 默认互惠。"""
    key = (intent.value, emotion.value, stage.value)
    triggers = DECISION_MATRIX.get(key)
    if triggers:
        return triggers
    # 部分匹配：intent + stage
    for k, v in DECISION_MATRIX.items():
        if k[0] == intent.value and k[2] == stage.value:
            return v
    return [TriggerType.RECIPROCITY]


def build_psych_block(triggers: list[TriggerType], stage: CustomerStage) -> str:
    """拼成可塞 system prompt 的话术指令块。"""
    if not triggers:
        return ""
    lines = [f"# 销售心理触发器（自动选 · 当前对话阶段：{stage.value}）"]
    for t in triggers:
        instr = TRIGGER_INSTRUCTIONS.get(t)
        if instr:
            lines.append("")
            lines.append(instr)
    return "\n".join(lines)


def recommend(
    intent: IntentEnum,
    emotion: EmotionEnum,
    last_intent: Optional[str] = None,
    last_intents_history: Optional[list[str]] = None,
    has_purchase_history: bool = False,
    days_since_last_message: Optional[int] = None,
    days_since_last_purchase: Optional[int] = None,
) -> TriggerRecommendation:
    """一站式 · 阶段识别 + 触发器推荐 + 话术拼接。"""
    stage = detect_stage(
        last_intent=last_intent,
        last_intents_history=last_intents_history,
        has_purchase_history=has_purchase_history,
        days_since_last_message=days_since_last_message,
        days_since_last_purchase=days_since_last_purchase,
    )
    triggers = recommend_triggers(intent, emotion, stage)
    instructions = build_psych_block(triggers, stage)
    return TriggerRecommendation(triggers=triggers, stage=stage, instructions=instructions)
