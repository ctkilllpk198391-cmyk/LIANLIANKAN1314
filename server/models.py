"""SQLAlchemy ORM · 全部数据表。

历史 6 张：tenants / messages / suggestions / reviews / sent_messages / audit_log
First Wave 2026-04-16 新增 7 张：
  customer_profiles / knowledge_chunks / follow_up_tasks
  account_health_metrics / account_health_status / account_failover_log
  training_queue
"""

from __future__ import annotations

from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id = Column(String(64), primary_key=True)
    boss_name = Column(String(128), nullable=False)
    plan = Column(String(32), nullable=False, default="trial")
    created_at = Column(Integer, nullable=False)
    config_json = Column(Text)


class Message(Base):
    __tablename__ = "messages"

    msg_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), ForeignKey("tenants.tenant_id"), nullable=False)
    chat_id = Column(String(128), nullable=False)
    sender_id = Column(String(128), nullable=False)
    sender_name = Column(String(128))
    text = Column(Text, nullable=False)
    msg_type = Column(String(32), nullable=False, default="text")
    timestamp = Column(Integer, nullable=False)
    raw_metadata = Column(Text)


Index("idx_messages_tenant", Message.tenant_id)
Index("idx_messages_chat", Message.tenant_id, Message.chat_id)


class Suggestion(Base):
    __tablename__ = "suggestions"

    msg_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    inbound_msg_id = Column(String(64), ForeignKey("messages.msg_id"), nullable=False)
    intent = Column(String(32), nullable=False)
    risk = Column(String(16), nullable=False)
    text = Column(Text, nullable=False)
    model_route = Column(String(64), nullable=False)
    generated_at = Column(Integer, nullable=False)
    similarity_check_passed = Column(Integer, nullable=False, default=1)
    rewrite_count = Column(Integer, nullable=False, default=0)
    forbidden_word_hit = Column(Integer, nullable=False, default=0)


Index("idx_suggestions_tenant", Suggestion.tenant_id)


class Review(Base):
    __tablename__ = "reviews"

    msg_id = Column(String(64), ForeignKey("suggestions.msg_id"), primary_key=True)
    decision = Column(String(16), nullable=False)
    edited_text = Column(Text)
    reviewed_at = Column(Integer, nullable=False)


class SentMessage(Base):
    __tablename__ = "sent_messages"

    msg_id = Column(String(64), ForeignKey("suggestions.msg_id"), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    chat_id = Column(String(128), nullable=False)
    text = Column(Text, nullable=False)
    sent_at = Column(Integer, nullable=False)
    success = Column(Integer, nullable=False)
    error = Column(Text)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    actor = Column(String(32), nullable=False)
    action = Column(String(64), nullable=False)
    tenant_id = Column(String(64), nullable=False)
    msg_id = Column(String(64))
    meta = Column(Text)
    timestamp = Column(Integer, nullable=False)


Index("idx_audit_tenant", AuditLog.tenant_id, AuditLog.timestamp)


# ─── First Wave 2026-04-16 ─────────────────────────────────────────────────

class CustomerProfile(Base):
    """F2 · 每个 contact 一份动态档案 · AI 回复时引用。"""

    __tablename__ = "customer_profiles"
    __table_args__ = (UniqueConstraint("tenant_id", "chat_id", name="uq_customer_tenant_chat"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False)
    chat_id = Column(String(128), nullable=False)
    nickname = Column(String(128))
    preferred_addressing = Column(String(64))
    vip_tier = Column(String(8), nullable=False, default="C")
    purchase_history = Column(Text)        # JSON list
    sensitive_topics = Column(Text)        # JSON list
    tags = Column(Text)                    # JSON list
    last_intent = Column(String(32))
    last_emotion = Column(String(32))
    last_message_at = Column(Integer)
    total_messages = Column(Integer, nullable=False, default=0)
    accepted_replies = Column(Integer, nullable=False, default=0)
    notes = Column(Text)
    updated_at = Column(Integer, nullable=False)


Index("idx_customer_tenant", CustomerProfile.tenant_id)
Index("idx_customer_lastmsg", CustomerProfile.tenant_id, CustomerProfile.last_message_at.desc())


class KnowledgeChunk(Base):
    """F3 · 老板上传产品/价格/库存知识 · embedding 召回。"""

    __tablename__ = "knowledge_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False)
    source = Column(String(256), nullable=False)
    chunk_text = Column(Text, nullable=False)
    embedding = Column(Text, nullable=False)   # JSON list[float] 384 维
    tags = Column(Text)                        # JSON list
    created_at = Column(Integer, nullable=False)


Index("idx_knowledge_tenant", KnowledgeChunk.tenant_id)
Index("idx_knowledge_source", KnowledgeChunk.tenant_id, KnowledgeChunk.source)


class FollowUpTask(Base):
    """F4 · 跟进序列 · APScheduler tick 触发。"""

    __tablename__ = "follow_up_tasks"

    task_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    chat_id = Column(String(128), nullable=False)
    sender_name = Column(String(128))
    task_type = Column(String(32), nullable=False)
    scheduled_at = Column(Integer, nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    template_id = Column(String(64))
    context_json = Column(Text)
    created_at = Column(Integer, nullable=False)
    sent_at = Column(Integer)


Index("idx_followup_due", FollowUpTask.status, FollowUpTask.scheduled_at)
Index("idx_followup_tenant", FollowUpTask.tenant_id, FollowUpTask.status)


class AccountHealthMetric(Base):
    """F6 · 5 维度健康指标时序记录。"""

    __tablename__ = "account_health_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False)
    account_id = Column(String(64), nullable=False)
    metric_name = Column(String(64), nullable=False)
    value = Column(Float, nullable=False)
    recorded_at = Column(Integer, nullable=False)


Index("idx_health_tenant", AccountHealthMetric.tenant_id, AccountHealthMetric.account_id, AccountHealthMetric.recorded_at.desc())


class AccountHealthStatus(Base):
    """F6 · 当前账号健康综合状态。"""

    __tablename__ = "account_health_status"
    __table_args__ = (UniqueConstraint("tenant_id", "account_id", name="uq_health_tenant_account"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False)
    account_id = Column(String(64), nullable=False)
    score = Column(Float, nullable=False)
    level = Column(String(16), nullable=False)
    daily_quota_override = Column(Integer)
    paused_until = Column(Integer)
    last_evaluated_at = Column(Integer, nullable=False)


class AccountFailoverLog(Base):
    """F7 · 账号容灾切换日志。"""

    __tablename__ = "account_failover_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False)
    from_account = Column(String(64), nullable=False)
    to_account = Column(String(64), nullable=False)
    reason = Column(String(256), nullable=False)
    triggered_at = Column(Integer, nullable=False)
    auto = Column(Integer, nullable=False, default=1)


Index("idx_failover_tenant", AccountFailoverLog.tenant_id, AccountFailoverLog.triggered_at.desc())


class TrainingQueue(Base):
    """C2 · 替代 industry_flywheel · 采纳/编辑/拒绝 → 训练数据队列。"""

    __tablename__ = "training_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False)
    customer_msg = Column(Text, nullable=False)
    ai_reply = Column(Text, nullable=False)
    final_text = Column(Text, nullable=False)
    decision = Column(String(16), nullable=False)
    intent = Column(String(32))
    emotion = Column(String(32))
    weight = Column(Float, nullable=False, default=1.0)
    created_at = Column(Integer, nullable=False)


Index("idx_training_tenant", TrainingQueue.tenant_id, TrainingQueue.created_at.desc())


# ─── Second Wave 2026-04-16 ────────────────────────────────────────────────

class MomentsPost(Base):
    """S8 · 朋友圈托管 · AI 写文案 + 定时发。"""

    __tablename__ = "moments_posts"

    post_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    post_type = Column(String(32), nullable=False)     # product/feedback/promo/lifestyle
    content = Column(Text, nullable=False)
    image_urls = Column(Text)                           # JSON list
    status = Column(String(16), nullable=False, default="draft")  # draft/scheduled/published/cancelled
    scheduled_at = Column(Integer)
    published_at = Column(Integer)
    created_at = Column(Integer, nullable=False)


Index("idx_moments_tenant", MomentsPost.tenant_id, MomentsPost.status)
Index("idx_moments_due", MomentsPost.status, MomentsPost.scheduled_at)


# ─── Third Wave · T5 数据所有权 ────────────────────────────────────────────

class DeletionRequest(Base):
    """T5 · 账号注销请求 · 30 天 grace period 后真删。"""

    __tablename__ = "deletion_requests"

    request_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    reason = Column(Text)
    status = Column(String(16), nullable=False, default="pending")  # pending/cancelled/executed
    requested_at = Column(Integer, nullable=False)
    grace_until = Column(Integer, nullable=False)
    executed_at = Column(Integer)


Index("idx_deletion_tenant", DeletionRequest.tenant_id, DeletionRequest.status)
Index("idx_deletion_grace", DeletionRequest.status, DeletionRequest.grace_until)


# ─── Third Wave · T1 内容摄入 + T2 营销方案 ────────────────────────────────

class ContentUpload(Base):
    """T1 · 老板魔法文件夹上传记录。"""

    __tablename__ = "content_uploads"

    file_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    file_name = Column(String(256), nullable=False)
    file_type = Column(String(32), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    parsed_chunks = Column(Integer, nullable=False, default=0)
    source_tag = Column(String(32))
    knowledge_chunk_ids = Column(Text)
    marketing_plan_id = Column(String(64))
    uploaded_at = Column(Integer, nullable=False)


Index("idx_content_tenant", ContentUpload.tenant_id, ContentUpload.uploaded_at.desc())


class MarketingPlan(Base):
    """T2 · 营销方案 · 朋友圈+SOP+群发完整套装。"""

    __tablename__ = "marketing_plans"

    plan_id = Column(String(64), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    source_content_id = Column(String(64))
    payload_json = Column(Text, nullable=False)
    status = Column(String(16), nullable=False, default="draft")
    activated_at = Column(Integer)
    created_at = Column(Integer, nullable=False)


Index("idx_marketing_tenant", MarketingPlan.tenant_id, MarketingPlan.status)


# ─── Fourth Wave · F2 激活码 + 设备绑定 ────────────────────────────────────

class ActivationCode(Base):
    """FDW F2 · 激活码 · 管理员发给客户 · 一次性激活。"""

    __tablename__ = "activation_codes"

    code = Column(String(64), primary_key=True)            # WXA-2026-XXXX-XXXX-XXXX
    plan = Column(String(32), nullable=False)              # trial/pro/flagship
    valid_days = Column(Integer, nullable=False)           # 30/365
    issued_at = Column(Integer, nullable=False)
    activated_at = Column(Integer)                          # null = 未激活
    activated_tenant_id = Column(String(64))               # 激活后绑定 tenant
    revoked = Column(Integer, nullable=False, default=0)


class DeviceBinding(Base):
    """FDW F2 · 设备绑定 · device_token 是 API 鉴权凭据。"""

    __tablename__ = "device_bindings"

    device_token = Column(String(128), primary_key=True)
    tenant_id = Column(String(64), nullable=False)
    activation_code = Column(String(64), ForeignKey("activation_codes.code"), nullable=False)
    machine_guid = Column(String(256), nullable=False)     # Windows Machine GUID
    bound_at = Column(Integer, nullable=False)
    last_heartbeat_at = Column(Integer, nullable=False)
    revoked = Column(Integer, nullable=False, default=0)


Index("idx_device_tenant", DeviceBinding.tenant_id)
Index("idx_device_code", DeviceBinding.activation_code)
