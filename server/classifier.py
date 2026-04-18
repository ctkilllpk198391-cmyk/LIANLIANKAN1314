"""IntentClassifier · rule + hybrid + LLM · 同时输出 emotion。

modes:
  - rule:    纯关键词（兼容老路径 · 测试用）
  - hybrid:  规则置信度 >= 0.6 → 用规则 · 补情绪规则；否则 LLM 兜底
  - llm:     全 LLM JSON-mode（贵 · 用于难判场景）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Literal, Optional

from shared.proto import IntentResult
from shared.types import EmotionEnum, IntentEnum, RiskEnum

logger = logging.getLogger(__name__)

INTENT_KEYWORDS: dict[IntentEnum, list[str]] = {
    IntentEnum.GREETING: ["在么", "在吗", "你好", "hello", "hi", "您好", "早上好", "晚上好"],
    IntentEnum.INQUIRY: ["多少钱", "价格", "怎么卖", "什么价", "报价", "几折", "优惠"],
    IntentEnum.NEGOTIATION: ["便宜", "贵了", "再便宜", "降点", "包邮", "送点", "划算", "比比"],
    IntentEnum.ORDER: ["要了", "下单", "买", "付款", "转账", "收款", "拍下", "确认"],
    IntentEnum.COMPLAINT: ["差评", "投诉", "退款", "假货", "骗子", "举报", "12315", "维权"],
    IntentEnum.SENSITIVE: ["合同", "发票", "退货", "退款", "追责", "律师", "法院"],
    IntentEnum.CHITCHAT: ["哈哈", "嗯嗯", "好的", "知道了", "谢谢", "ok", "okay"],
}

RISK_INTENT_MAP = {
    IntentEnum.SENSITIVE: RiskEnum.HIGH,
    IntentEnum.COMPLAINT: RiskEnum.HIGH,
    IntentEnum.ORDER: RiskEnum.MEDIUM,
    IntentEnum.NEGOTIATION: RiskEnum.MEDIUM,
    IntentEnum.INQUIRY: RiskEnum.LOW,
    IntentEnum.GREETING: RiskEnum.LOW,
    IntentEnum.CHITCHAT: RiskEnum.LOW,
    IntentEnum.UNKNOWN: RiskEnum.LOW,
}

# 情绪规则（fast path · 不调 LLM）
ANGRY_KEYWORDS = ["差评", "投诉", "退货", "退款", "骗", "气", "无语", "失望", "垃圾", "维权"]
ANXIOUS_KEYWORDS = ["急", "马上", "立刻", "等不及", "快点", "赶紧", "在吗??"]
EXCITED_KEYWORDS = ["买买买", "现在就要", "马上下单", "我要", "拍了"]


class IntentClassifier:
    HYBRID_RULE_CONFIDENCE = 0.6

    def __init__(
        self,
        mode: Literal["rule", "llm", "hybrid"] = "hybrid",
        llm_client=None,  # LLMClient instance
        llm_route: str = "deepseek_v32",
    ):
        self.mode = mode
        self.llm_client = llm_client
        self.llm_route = llm_route

    async def classify(self, text: str, history: Optional[list[str]] = None) -> IntentResult:
        rule_result = self._classify_rule(text)
        rule_result.emotion = self._guess_emotion_rule(text)

        if self.mode == "rule":
            return rule_result

        if self.mode == "hybrid":
            if rule_result.confidence >= self.HYBRID_RULE_CONFIDENCE:
                return rule_result
            # 低置信度 · LLM 兜底
            llm_result = await self._classify_llm(text, history)
            return llm_result if llm_result is not None else rule_result

        # mode == "llm"
        llm_result = await self._classify_llm(text, history)
        return llm_result if llm_result is not None else rule_result

    @staticmethod
    def _classify_rule(text: str) -> IntentResult:
        text_l = text.lower()
        best_intent = IntentEnum.UNKNOWN
        best_score = 0
        matched: list[str] = []

        for intent, keywords in INTENT_KEYWORDS.items():
            local_hits = [k for k in keywords if k.lower() in text_l]
            if len(local_hits) > best_score:
                best_score = len(local_hits)
                best_intent = intent
                matched = local_hits

        risk = RISK_INTENT_MAP[best_intent]
        money_kw = ["¥", "元", "块钱", "万", "千", "百", "钱", "块"]
        if any(kw in text for kw in money_kw):
            if risk == RiskEnum.LOW:
                risk = RiskEnum.MEDIUM

        for big in ("万", "千元", "千块"):
            if big in text:
                risk = RiskEnum.HIGH
                break

        confidence = min(1.0, 0.4 + 0.2 * best_score) if best_intent != IntentEnum.UNKNOWN else 0.3

        return IntentResult(
            intent=best_intent,
            confidence=confidence,
            risk=risk,
            emotion=EmotionEnum.CALM,  # 待 _guess_emotion_rule 覆盖
            matched_keywords=matched,
        )

    @staticmethod
    def _guess_emotion_rule(text: str) -> EmotionEnum:
        if any(k in text for k in ANGRY_KEYWORDS):
            return EmotionEnum.ANGRY
        if any(k in text for k in EXCITED_KEYWORDS):
            return EmotionEnum.EXCITED
        if any(k in text for k in ANXIOUS_KEYWORDS):
            return EmotionEnum.ANXIOUS
        # ? 数 ≥ 3 → ANXIOUS
        if text.count("?") + text.count("？") >= 3:
            return EmotionEnum.ANXIOUS
        # 短句 + ! 多 → EXCITED
        if len(text) <= 10 and (text.count("!") + text.count("！")) >= 2:
            return EmotionEnum.EXCITED
        return EmotionEnum.CALM

    async def _classify_llm(self, text: str, history: Optional[list[str]] = None) -> Optional[IntentResult]:
        """LLM JSON-mode · 同时返 intent + emotion + risk。失败返 None。"""
        if self.llm_client is None:
            logger.debug("classify_llm: no llm_client · skip")
            return None

        history_str = ""
        if history:
            history_str = "\n# 最近对话\n" + "\n".join(f"- {h}" for h in history[-3:])

        prompt = (
            "判断客户消息的意图、情绪、风险等级。只返回 JSON · 不要解释。\n"
            f"消息：{text}{history_str}\n\n"
            "返回 JSON 格式（不要任何前缀/后缀）：\n"
            '{"intent": "greeting|inquiry|negotiation|order|complaint|chitchat|sensitive|unknown", '
            '"emotion": "calm|anxious|angry|excited", '
            '"risk": "low|medium|high", '
            '"confidence": 0.0-1.0}'
        )

        try:
            raw = await self.llm_client.respond(
                prompt=prompt,
                tenant_id="_classifier_",
                model_route=self.llm_route,
                max_tokens=120,
                system="你是一个意图+情绪分类器。严格只输出 JSON。",
            )
            data = _extract_json(raw)
            if not data:
                return None
            return IntentResult(
                intent=IntentEnum(data.get("intent", "unknown")),
                emotion=EmotionEnum(data.get("emotion", "calm")),
                risk=RiskEnum(data.get("risk", "low")),
                confidence=float(data.get("confidence", 0.7)),
                matched_keywords=[],
            )
        except Exception as e:
            logger.warning("classify_llm failed: %s · raw=%s", e, raw[:120] if "raw" in dir() else "")
            return None


def _extract_json(raw: str) -> Optional[dict]:
    """容错 · 找第一个 { ... } 块。"""
    if not raw:
        return None
    match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
