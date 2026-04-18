# Phase 1 · Self-Zero Demo · Design

> Spec ID：`phase1_self_zero_demo`
> 起草日期：2026-04-15

---

## 1. 架构总览

```
┌──────────────── Windows 客户端（wechat_agent client） ────────────────┐
│                                                                       │
│  ┌─ watcher.py ──────┐  ┌─ review_popup.py ─┐  ┌─ sender.py ────┐    │
│  │ wxautox 监听新消息 │→│ Console/Qt6 浮窗  │→│ HumanCursor 发送 │    │
│  └──────┬────────────┘  └────────┬──────────┘  └────────┬───────┘    │
│         │                         │                       │           │
│         │ inbound msg            │ accept/edit/reject    │ sent ack  │
│         ▼                         ▼                       ▼           │
│  ┌────────────────── shared/proto.py（Pydantic 协议）────────────┐    │
│  │  InboundMsg / Suggestion / ReviewDecision / SendAck           │    │
│  └────────────────────────────┬───────────────────────────────────┘    │
│                                │                                       │
│                                │ HTTPS WSS（mTLS Phase 4）             │
└────────────────────────────────┼───────────────────────────────────────┘
                                 │
┌────────────────────────────────▼───────────────────────────────────────┐
│                  macOS 服务端（wechat_agent server · port 8327）        │
│                                                                         │
│  ┌─ main.py（FastAPI）──────────────────────────────────────────────┐   │
│  │  POST /v1/inbound          → 接收新消息                          │   │
│  │  POST /v1/outbound/:id/accept  → 老板采纳                        │   │
│  │  POST /v1/outbound/:id/reject  → 老板拒绝                        │   │
│  │  POST /v1/outbound/:id/edit    → 老板改后发                      │   │
│  │  GET  /v1/health           → 健康检查                            │   │
│  │  GET  /v1/tenant/:id/dashboard → 老板看板（Phase 5 完整）         │   │
│  └────────────────┬─────────────────────────────────────────────────┘   │
│                   │                                                     │
│                   ▼                                                     │
│  ┌─ tenant.py ──────────────┐  ┌─ audit.py ─────────────────┐         │
│  │ get_tenant(tenant_id)     │  │ log_event(actor, action,    │         │
│  │ enforce_isolation()       │  │   tenant_id, msg_id, meta)  │         │
│  └──────────┬────────────────┘  └────────────┬───────────────┘         │
│             │                                 │                         │
│             ▼                                 ▼                         │
│  ┌─ classifier.py ───┐  ┌─ generator.py ──┐  ┌─ hermes_bridge.py ──┐ │
│  │ intent: 询价/砍价/ │→│ generate(msg,    │→│ POST hermes-agent   │ │
│  │   下单/投诉/闲聊   │  │  tenant, intent) │  │  /v1/agent/respond  │ │
│  └────────────────────┘  └────────┬─────────┘  └──────────────────────┘ │
│                                    │                                    │
│                                    ▼                                    │
│  ┌─ model_router.py ──────────────────────────────────────────────┐    │
│  │ Phase 1: hardcoded route → hermes_bridge                       │    │
│  │ Phase 3: vLLM 多 LoRA 热切换（lora_id = tenant_id）            │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                                                         │
│  ┌─ DB（SQLAlchemy · SQLite Phase 1, PostgreSQL+pgvector Phase 2）──┐  │
│  │  tenants / messages / suggestions / reviews / audit_log         │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 数据流（端到端 Happy Path）

```
1. 客户给老板发消息
   → wxautox 触发 watcher.on_message(chat_id, sender, text)

2. watcher 调用 risk_control.is_workhour() 检查
   → 否则丢入 deferred queue（明早 9 点处理）

3. watcher 包装为 InboundMsg → POST /v1/inbound
   {
     "tenant_id": "tenant_001",
     "chat_id": "wxid_xxx",
     "sender_id": "wxid_yyy",
     "sender_name": "客户A",
     "text": "在么？",
     "timestamp": 1713188400,
     "msg_type": "text"
   }

4. server.main 收到 → tenant.enforce_isolation() → 写 messages 表
   → audit.log_event(actor="client", action="inbound_received", ...)

5. classifier.classify(text) → IntentResult { intent: "greeting", risk: "low" }
   → 写 suggestions.intent

6. generator.generate(msg, tenant, intent)
   → 调用 hermes_bridge.respond(prompt, tenant_id, model_route)
   → hermes-agent 返回文本（Phase 3 走 vLLM LoRA）

7. risk_control.dedup_check(suggestion, tenant_id, window=7d)
   → 相似度 >60% 强制 generator 重写一次（最多 3 次）

8. 写 suggestions 表 + audit.log_event(action="suggestion_generated")
   → 长轮询/WSS 推到 client

9. client review_popup 弹窗（Phase 1 console.input；Phase 3 Qt6）
   → 老板按 [a]ccept / [e]dit / [r]eject

10. client POST /v1/outbound/:msg_id/accept （或 edit/reject）
    → audit.log_event(action="reviewed", decision=...)

11. accept 路径：sender.send(chat_id, text) 用 HumanCursor 模拟人手
    → wxautox.SendMsg
    → audit.log_event(action="sent")

12. 完成。整条链 5 个 audit 节点，可追溯。
```

---

## 3. 模块接口设计

### 3.1 shared/proto.py（Pydantic）

```python
class InboundMsg(BaseModel):
    tenant_id: str
    chat_id: str
    sender_id: str
    sender_name: str
    text: str
    timestamp: int
    msg_type: Literal["text", "image", "voice", "card"] = "text"
    raw_metadata: dict = {}

class IntentResult(BaseModel):
    intent: Literal["greeting","inquiry","negotiation","order","complaint","chitchat","sensitive"]
    confidence: float
    risk: Literal["low","medium","high"]

class Suggestion(BaseModel):
    msg_id: str
    tenant_id: str
    inbound_msg_id: str
    intent: IntentResult
    text: str
    model_route: str  # "hermes_default" | "lora:tenant_001" | "claude_sonnet"
    generated_at: int
    similarity_check_passed: bool

class ReviewDecision(BaseModel):
    msg_id: str
    decision: Literal["accept","edit","reject"]
    edited_text: Optional[str] = None
    reviewer_at: int

class SendAck(BaseModel):
    msg_id: str
    sent_at: int
    success: bool
    error: Optional[str] = None
```

### 3.2 server/classifier.py

```python
class IntentClassifier:
    def __init__(self, mode: Literal["rule","llm","hybrid"] = "rule"): ...
    async def classify(self, text: str, ctx: dict) -> IntentResult: ...
```

Phase 1: 规则版本（关键词匹配）够用。
Phase 3: 升级 LLM 版本（Qwen3-4B 本地）。

### 3.3 server/generator.py

```python
class ReplyGenerator:
    def __init__(self, hermes_bridge, model_router): ...
    async def generate(
        self,
        msg: InboundMsg,
        tenant: Tenant,
        intent: IntentResult,
    ) -> Suggestion: ...
```

### 3.4 server/model_router.py

```python
class ModelRouter:
    """Phase 1 hardcoded 走 hermes_bridge; Phase 3 接 vLLM 多 LoRA。"""
    def route(self, tenant_id: str, intent: IntentResult) -> str:
        # 返回 model_route 字符串
        # Phase 1: 永远返回 "hermes_default"
        # Phase 3: tenant LoRA 已训 → "lora:{tenant_id}"
        #         risk=high → "claude_sonnet"
        #         其他 → "deepseek_v32"
```

### 3.5 server/hermes_bridge.py

```python
class HermesBridge:
    def __init__(self, base_url: str, mock: bool = False): ...
    async def respond(
        self,
        prompt: str,
        tenant_id: str,
        model_route: str,
        max_tokens: int = 300,
    ) -> str: ...
```

### 3.6 server/tenant.py

```python
class TenantManager:
    def get(self, tenant_id: str) -> Tenant: ...
    def enforce_isolation(self, request_tenant: str, resource_tenant: str): ...
        # raise CrossTenantError if mismatch
```

### 3.7 server/audit.py

```python
class AuditLogger:
    async def log_event(
        self,
        actor: str,           # "client"|"server"|"hermes"|"reviewer"
        action: str,          # "inbound_received"|"suggestion_generated"|...
        tenant_id: str,
        msg_id: Optional[str] = None,
        meta: dict = {},
    ): ...
```

### 3.8 client/watcher.py

```python
class WeChatWatcher:
    def __init__(self, server_url: str, tenant_id: str, mock: bool = False):
        # mock=True 用于 macOS 测试
        # mock=False 时 import wxautox（仅 Windows 可成功）
        ...
    async def start(self): ...
    async def on_message(self, chat_id, sender, text): ...
```

### 3.9 client/risk_control.py

```python
class RiskController:
    def is_workhour(self, now: datetime, schedule: WorkSchedule) -> bool: ...
    def quota_remaining(self, tenant_id: str, today_count: int) -> int: ...
    def is_duplicate(self, text: str, tenant_id: str, window_days: int = 7) -> bool: ...
    def dedup_rewrite_required(self, text: str, tenant_id: str) -> bool: ...
```

### 3.10 client/sender.py

```python
class HumanLikeSender:
    def __init__(self, mock: bool = False): ...
    async def send(self, chat_id: str, text: str) -> SendAck: ...
        # 真模式：HumanCursor 移动 → wxautox.SendMsg
        # mock 模式：sleep + 返回 success
```

---

## 4. 数据库 Schema（SQLite Phase 1 兼容 PostgreSQL Phase 2）

```sql
-- tenants
CREATE TABLE tenants (
    tenant_id TEXT PRIMARY KEY,
    boss_name TEXT NOT NULL,
    plan TEXT NOT NULL DEFAULT 'trial',  -- trial/pro/flagship
    created_at INTEGER NOT NULL,
    config_json TEXT  -- JSON: work_schedule, daily_quota, customizations
);

-- messages（inbound）
CREATE TABLE messages (
    msg_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    sender_id TEXT NOT NULL,
    sender_name TEXT,
    text TEXT NOT NULL,
    msg_type TEXT NOT NULL DEFAULT 'text',
    timestamp INTEGER NOT NULL,
    raw_metadata TEXT,  -- JSON
    FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
);
CREATE INDEX idx_messages_tenant ON messages(tenant_id);
CREATE INDEX idx_messages_chat ON messages(tenant_id, chat_id);

-- suggestions（AI 生成的回复）
CREATE TABLE suggestions (
    msg_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    inbound_msg_id TEXT NOT NULL,
    intent TEXT NOT NULL,
    risk TEXT NOT NULL,
    text TEXT NOT NULL,
    model_route TEXT NOT NULL,
    generated_at INTEGER NOT NULL,
    similarity_check_passed INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (inbound_msg_id) REFERENCES messages(msg_id)
);

-- reviews（老板的决定）
CREATE TABLE reviews (
    msg_id TEXT PRIMARY KEY,
    decision TEXT NOT NULL,  -- accept/edit/reject
    edited_text TEXT,
    reviewed_at INTEGER NOT NULL,
    FOREIGN KEY (msg_id) REFERENCES suggestions(msg_id)
);

-- sent（实际发出去的）
CREATE TABLE sent_messages (
    msg_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    text TEXT NOT NULL,
    sent_at INTEGER NOT NULL,
    success INTEGER NOT NULL,
    error TEXT,
    FOREIGN KEY (msg_id) REFERENCES suggestions(msg_id)
);

-- 审计日志（合规核心）
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    msg_id TEXT,
    meta TEXT,  -- JSON
    timestamp INTEGER NOT NULL
);
CREATE INDEX idx_audit_tenant ON audit_log(tenant_id, timestamp);
```

---

## 5. 配置层

### 5.1 config/config.example.yaml

```yaml
server:
  host: 0.0.0.0
  port: 8327
  tenant_default_plan: trial

database:
  driver: sqlite       # sqlite | postgres（Phase 2 切换）
  url: sqlite:///./data/wechat_agent.db
  # postgres: postgresql+asyncpg://user:pass@localhost/hermes_baiyang

hermes:
  base_url: http://127.0.0.1:8317   # hermes-agent 默认端口
  mock: true                         # Phase 1 默认 mock，等 hermes 正常再切

risk_control:
  daily_quota_default: 30
  daily_quota_seasoned: 100
  daily_quota_max: 150
  dedup_window_days: 7
  dedup_threshold: 0.6
  workhour_start: "09:00"
  workhour_end: "21:00"
  heartbeat_min_hours: 9
  heartbeat_max_hours: 11

audit:
  retention_days: 365
  log_to_file: ./logs/audit.jsonl

llm:
  classifier_mode: rule    # rule | llm | hybrid（Phase 3 升级）
  generator_max_tokens: 300
  generator_temp: 0.7
```

### 5.2 config/tenants.example.yaml

```yaml
tenants:
  - tenant_id: tenant_0001
    boss_name: 连大哥
    plan: pro
    work_schedule:
      monday:    {start: "09:00", end: "21:00"}
      tuesday:   {start: "09:00", end: "21:00"}
      wednesday: {start: "09:00", end: "21:00"}
      thursday:  {start: "09:00", end: "21:00"}
      friday:    {start: "09:00", end: "21:00"}
      saturday:  {start: "10:00", end: "18:00"}
      sunday:    {start: "10:00", end: "18:00"}
    daily_quota: 100
    style_hints: |
      回复风格：直接、简洁、带轻微幽默
      避免：过度客套、emoji 滥用
```

---

## 6. 测试策略

### 6.1 单元测试
- `test_proto.py`：所有 Pydantic 模型 round-trip 序列化
- `test_classifier.py`：规则分类 happy/edge case
- `test_risk_control.py`：工作时间 / 配额 / 去重三个核心
- `test_tenant.py`：跨 tenant 隔离强制

### 6.2 集成测试
- `test_main_api.py`：FastAPI TestClient 跑通 4 步 happy path
- `test_audit_chain.py`：消息全链 5 个 audit 节点齐全

### 6.3 mock 策略
- `wxautox` mock：`tests/mocks/wxautox_mock.py`
- `hermes-agent` mock：`HermesBridge(mock=True)` 返回固定文本

### 6.4 验收门
- `pytest tests/` 全绿
- `python -c "import server.main; ..."` 不报错
- coverage > 60%（Phase 1 不强求 80%）

---

## 7. Phase 1 → Phase 2 升级路径

| 模块 | Phase 1 | Phase 2 |
|---|---|---|
| DB | SQLite | PostgreSQL + pgvector |
| classifier | 规则 | Qwen3-4B 本地 LLM |
| generator | hermes_bridge mock 文本 | hermes_bridge 真调 + LoRA 训练后路由 |
| review_popup | console input | Qt6 浮窗 |
| 真跑环境 | macOS mock | Windows wxautox |
| 数据采集 | 无 | WeChatMsg 集成 |

---

## 8. 安全与合规

- 所有 `Suggestion.text` 在写入 DB 前过 `risk_control.contains_forbidden_words()`
  - 禁用词：保证/一定/终身/稳赚/无风险（MISSION 第 5 节）
  - 命中 → 标记 `risk=high` + `model_route=human_required`
- 跨 tenant 调用必须 `tenant.enforce_isolation()`，违者抛异常 + 写 audit
- 审计日志按 365 天保留（合规）
- 用户协议 / 隐私政策占位文件先建，Phase 5 法务定稿
