"""协议层 · client/server 通信的 Pydantic 模型。"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from shared.const import MAX_REPLY_LENGTH
from shared.types import EmotionEnum, IntentEnum, ReviewDecisionEnum, RiskEnum


class InboundMsg(BaseModel):
    """客户端 → 服务端 · 客户发来的新消息。"""

    tenant_id: str
    chat_id: str
    sender_id: str
    sender_name: str = ""
    text: str
    timestamp: int
    msg_type: Literal["text", "image", "voice", "card", "file"] = "text"
    image_url: Optional[str] = None
    voice_url: Optional[str] = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        return v.strip()


class IntentResult(BaseModel):
    intent: IntentEnum
    confidence: float = Field(ge=0.0, le=1.0)
    risk: RiskEnum
    emotion: EmotionEnum = EmotionEnum.CALM
    matched_keywords: list[str] = Field(default_factory=list)


class Suggestion(BaseModel):
    """服务端 → 客户端 · AI 生成的回复建议。"""

    msg_id: str
    tenant_id: str
    inbound_msg_id: str
    intent: IntentResult
    text: str
    model_route: str
    generated_at: int
    similarity_check_passed: bool = True
    rewrite_count: int = 0
    forbidden_word_hit: bool = False
    # Wave 14 · AI 用 [[IMG:filename]] 引用 · generator 解析后填入 · _dispatch_reply 先发图再发文
    image_filenames: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def _enforce_length(cls, v: str) -> str:
        if len(v) > MAX_REPLY_LENGTH:
            raise ValueError(f"reply exceeds {MAX_REPLY_LENGTH} chars (got {len(v)})")
        return v


class ReviewDecision(BaseModel):
    """客户端 → 服务端 · 老板审核决定。"""

    msg_id: str
    decision: ReviewDecisionEnum
    edited_text: Optional[str] = None
    reviewed_at: int


class SendAck(BaseModel):
    """客户端 → 服务端 · 发送结果回执。"""

    msg_id: str
    sent_at: int
    success: bool
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded", "down"] = "ok"
    version: str
    hermes_reachable: bool
    db_reachable: bool
    tenants_loaded: int


class TenantConfig(BaseModel):
    """tenant 配置，从 yaml 加载。"""

    tenant_id: str
    boss_name: str
    plan: str = "trial"
    daily_quota: int = 30
    workhour_start: str = "09:00"
    workhour_end: str = "21:00"
    style_hints: str = ""
    # First Wave F1 · 全自动引擎配置
    auto_send_enabled: bool = True
    high_risk_block: bool = True
    boss_phone_webhook: Optional[str] = None
    # First Wave F7 · 多账号配置
    accounts: list[dict] = Field(default_factory=list)
    active_account_id: Optional[str] = None
    # Second Wave S3 · 行业模板
    industry: str = "通用"
