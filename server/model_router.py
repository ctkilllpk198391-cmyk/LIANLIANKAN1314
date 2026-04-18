"""ModelRouter · 2026-04-15 v3 · "像真人" 优先 + 按 intent 选最佳模型。

核心洞察（来自 LMArena + BenchLM + 实证）：
- 通用强 ≠ 拟人强（DeepSeek 推理高但写出来像论文）
- 拟人冠军：Doubao 1.5 Pro（字节）+ MiniMax abab 6.5s（角色扮演专家）
- 高风险用 GLM-5.1（中文最强 + 合规稳）
- 推理用 DeepSeek（便宜 + 准）

按 intent 路由（不只看 risk）:
- greeting / chitchat / negotiation → 拟人优先 (Doubao)
- inquiry / order → 推理优先 (DeepSeek)
- complaint / sensitive → 安全优先 (GLM-5.1)
- LoRA 已训 → 客户专属分身 (vLLM)
"""

from __future__ import annotations

from shared.proto import IntentResult
from shared.types import IntentEnum, RiskEnum


# intent → 推荐 model（拟人 + 速度优先）
INTENT_TO_MODEL = {
    IntentEnum.GREETING: "doubao_15pro",          # 闲聊：拟人最强
    IntentEnum.CHITCHAT: "minimax_m25_lightning", # 短消息：100 TPS 极速响应
    IntentEnum.NEGOTIATION: "doubao_15pro",       # 砍价：需要共情 + 拟人
    IntentEnum.INQUIRY: "deepseek_v32",           # 询价：推理 + 便宜
    IntentEnum.ORDER: "deepseek_v32",             # 下单：精确 + 不出错
    IntentEnum.COMPLAINT: "glm_51",               # 投诉：中文最强 + 合规
    IntentEnum.SENSITIVE: "glm_51",               # 敏感：合规 + 安全
    IntentEnum.UNKNOWN: "minimax_m25_lightning",  # 未知 fallback：极速
}


class ModelRouter:
    """根据 intent + risk + LoRA 可用性决定路由名。"""

    def __init__(self, lora_ready: dict[str, bool] | None = None):
        self.lora_ready = lora_ready or {}

    def route(self, tenant_id: str, intent: IntentResult) -> str:
        # 优先级 1: LoRA 已训 → 客户专属分身（最像老板）
        if self.lora_ready.get(tenant_id):
            return "local_vllm"

        # 优先级 2: 高风险 一律 GLM-5.1（无视 intent 优先级）
        if intent.risk == RiskEnum.HIGH:
            return "glm_51"

        # 优先级 3: 按 intent 选最佳模型
        return INTENT_TO_MODEL.get(intent.intent, "doubao_15pro")

    def mark_lora_ready(self, tenant_id: str) -> None:
        self.lora_ready[tenant_id] = True

    def mark_lora_unready(self, tenant_id: str) -> None:
        self.lora_ready.pop(tenant_id, None)
