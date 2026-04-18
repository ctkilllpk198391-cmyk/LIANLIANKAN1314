-- 白羊 wechat_agent · DB Schema · Phase 1 兼容 SQLite/PostgreSQL
-- Phase 2 升 PostgreSQL 时增加 pgvector 扩展

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id TEXT PRIMARY KEY,
    boss_name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'trial',
    created_at INTEGER NOT NULL,
    config_json TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    msg_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT,
    text TEXT NOT NULL,
    msg_type TEXT NOT NULL DEFAULT 'text',
    timestamp INTEGER NOT NULL,
    raw_metadata TEXT,
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_tenant ON messages(tenant_id);
CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(tenant_id, chat_id);

CREATE TABLE IF NOT EXISTS suggestions (
    msg_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    inbound_msg_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    risk TEXT NOT NULL,
    text TEXT NOT NULL,
    model_route TEXT NOT NULL,
    generated_at INTEGER NOT NULL,
    similarity_check_passed INTEGER NOT NULL DEFAULT 1,
    rewrite_count INTEGER NOT NULL DEFAULT 0,
    forbidden_word_hit INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (inbound_msg_id) REFERENCES messages(msg_id)
);
CREATE INDEX IF NOT EXISTS idx_suggestions_tenant ON suggestions(tenant_id);

CREATE TABLE IF NOT EXISTS reviews (
    msg_id TEXT PRIMARY KEY,
    decision TEXT NOT NULL,
    edited_text TEXT,
    reviewed_at INTEGER NOT NULL,
    FOREIGN KEY (msg_id) REFERENCES suggestions(msg_id)
);

CREATE TABLE IF NOT EXISTS sent_messages (
    msg_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    text TEXT NOT NULL,
    sent_at INTEGER NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    FOREIGN KEY (msg_id) REFERENCES suggestions(msg_id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    msg_id TEXT,
    meta TEXT,
    timestamp INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_tenant ON audit_log(tenant_id, timestamp);

-- ─── First Wave 2026-04-16 ─────────────────────────────────────────────────

-- F2 客户档案
CREATE TABLE IF NOT EXISTS customer_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    nickname TEXT,
    preferred_addressing TEXT,
    vip_tier TEXT NOT NULL DEFAULT 'C',
    purchase_history TEXT,
    sensitive_topics TEXT,
    tags TEXT,
    last_intent TEXT,
    last_emotion TEXT,
    last_message_at INTEGER,
    total_messages INTEGER NOT NULL DEFAULT 0,
    accepted_replies INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    updated_at INTEGER NOT NULL,
    UNIQUE(tenant_id, chat_id)
);
CREATE INDEX IF NOT EXISTS idx_customer_tenant ON customer_profiles(tenant_id);
CREATE INDEX IF NOT EXISTS idx_customer_lastmsg ON customer_profiles(tenant_id, last_message_at DESC);

-- F3 知识库 RAG
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    source TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding TEXT NOT NULL,
    tags TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_knowledge_tenant ON knowledge_chunks(tenant_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_source ON knowledge_chunks(tenant_id, source);

-- F4 跟进序列
CREATE TABLE IF NOT EXISTS follow_up_tasks (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    sender_name TEXT,
    task_type TEXT NOT NULL,
    scheduled_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    template_id TEXT,
    context_json TEXT,
    created_at INTEGER NOT NULL,
    sent_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_followup_due ON follow_up_tasks(status, scheduled_at);
CREATE INDEX IF NOT EXISTS idx_followup_tenant ON follow_up_tasks(tenant_id, status);

-- F6 反封号 · 5 维度指标
CREATE TABLE IF NOT EXISTS account_health_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value REAL NOT NULL,
    recorded_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_health_tenant ON account_health_metrics(tenant_id, account_id, recorded_at DESC);

-- F6 反封号 · 当前状态
CREATE TABLE IF NOT EXISTS account_health_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    score REAL NOT NULL,
    level TEXT NOT NULL,
    daily_quota_override INTEGER,
    paused_until INTEGER,
    last_evaluated_at INTEGER NOT NULL,
    UNIQUE(tenant_id, account_id)
);

-- F7 多账号容灾日志
CREATE TABLE IF NOT EXISTS account_failover_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    from_account TEXT NOT NULL,
    to_account TEXT NOT NULL,
    reason TEXT NOT NULL,
    triggered_at INTEGER NOT NULL,
    auto INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_failover_tenant ON account_failover_log(tenant_id, triggered_at DESC);

-- C2 训练数据队列（替代 industry_flywheel）
CREATE TABLE IF NOT EXISTS training_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    customer_msg TEXT NOT NULL,
    ai_reply TEXT NOT NULL,
    final_text TEXT NOT NULL,
    decision TEXT NOT NULL,
    intent TEXT,
    emotion TEXT,
    weight REAL NOT NULL DEFAULT 1.0,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_training_tenant ON training_queue(tenant_id, created_at DESC);

-- S8 朋友圈托管
CREATE TABLE IF NOT EXISTS moments_posts (
    post_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    post_type TEXT NOT NULL,      -- product/feedback/promo/lifestyle
    content TEXT NOT NULL,
    image_urls TEXT,              -- JSON list
    status TEXT NOT NULL DEFAULT 'draft', -- draft/scheduled/published/cancelled
    scheduled_at INTEGER,
    published_at INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_moments_tenant ON moments_posts(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_moments_due ON moments_posts(status, scheduled_at);

-- T5 数据所有权 · 删除请求
CREATE TABLE IF NOT EXISTS deletion_requests (
    request_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/cancelled/executed
    requested_at INTEGER NOT NULL,
    grace_until INTEGER NOT NULL,
    executed_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_deletion_tenant ON deletion_requests(tenant_id, status);

-- T1 内容摄入 · 魔法文件夹
CREATE TABLE IF NOT EXISTS content_uploads (
    file_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    parsed_chunks INTEGER NOT NULL DEFAULT 0,
    source_tag TEXT,
    knowledge_chunk_ids TEXT,
    marketing_plan_id TEXT,
    uploaded_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_content_tenant ON content_uploads(tenant_id, uploaded_at DESC);

-- T2 营销方案
CREATE TABLE IF NOT EXISTS marketing_plans (
    plan_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source_content_id TEXT,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',  -- draft/active/cancelled
    activated_at INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_marketing_tenant ON marketing_plans(tenant_id, status);
CREATE INDEX IF NOT EXISTS idx_deletion_grace ON deletion_requests(status, grace_until);

-- FDW F2 激活码系统
CREATE TABLE IF NOT EXISTS activation_codes (
    code TEXT PRIMARY KEY,           -- "WXA-2026-A1B2-C3D4-E5F6"
    plan TEXT NOT NULL,              -- trial/pro/flagship
    valid_days INTEGER NOT NULL,     -- 30/365
    issued_at INTEGER NOT NULL,
    activated_at INTEGER,            -- 激活时间 · null=未激活
    activated_tenant_id TEXT,        -- 激活后绑定 tenant
    revoked INTEGER NOT NULL DEFAULT 0
);

-- FDW F2 设备绑定
CREATE TABLE IF NOT EXISTS device_bindings (
    device_token TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    activation_code TEXT NOT NULL,
    machine_guid TEXT NOT NULL,      -- Windows Machine GUID
    bound_at INTEGER NOT NULL,
    last_heartbeat_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_device_tenant ON device_bindings(tenant_id);
CREATE INDEX IF NOT EXISTS idx_device_code ON device_bindings(activation_code);
