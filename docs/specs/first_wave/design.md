# First Wave · Design · 技术方案

> 配套文件：`requirements.md` · `tasks.md`
> 目标读者：童虎自己 + 后续维护者
> 设计原则：第一性原理 · 奥卡姆剃刀 · 不引论文级架构

---

## 一、全自动数据流（v2 · 替代之前"副驾驶审核"流）

```
┌─ 客户微信发消息 ────────────────────────────┐
│ wxauto on_message → client.watcher          │
│ → POST /v1/inbound                          │
└─────────────┬───────────────────────────────┘
              ▼
┌─ server.main /v1/inbound ──────────────────┐
│ 1. tenant.enforce_isolation                 │
│ 2. classifier.classify (rule + emotion)     │
│ 3. customer_profile.get(chat_id) ← F2       │
│ 4. knowledge_base.recall_top_k(text) ← F3   │
│ 5. prompt_builder.build (incl. profile+RAG) │
│ 6. generator.generate                       │
│ 7. risk_check.contains_forbidden + dedup    │
│ 8. ↓ 决策分支                                │
└─────────────┬───────────────────────────────┘
              ▼
┌─ AutoSendDecider ← F1 ─────────────────────┐
│ if risk == HIGH or quota_exceeded:          │
│   → audit "auto_send_blocked"               │
│   → push 老板手机通知（异步）                │
│   → 不发                                     │
│ elif tenant.auto_send_enabled and healthy: │
│   → 直接 push WS → client.sender 自动发     │
│ else:                                       │
│   → 进 review queue（老板手动看）            │
└─────────────┬───────────────────────────────┘
              ▼
┌─ client.sender ─────────────────────────────┐
│ HumanCursor 模拟人 + wxauto.SendMsg         │
│ → POST /v1/outbound/{msg_id}/sent           │
└─────────────┬───────────────────────────────┘
              ▼
┌─ 后处理（async） ───────────────────────────┐
│ - customer_profile.update_after_reply       │
│ - health_monitor.record_send                │
│ - follow_up.maybe_schedule (if order intent)│
│ - training_queue.append (if accepted)       │
└─────────────────────────────────────────────┘

并行后台 jobs（APScheduler）:
├─ 每 1 分钟: follow_up.tick (扫到点的 task)
├─ 每 5 分钟: health_monitor.score_all
├─ 每天 02:00: customer_profile.weekly_compact
└─ 每周一 09:00: dashboard.weekly_report → 飞书
```

---

## 二、F1 · 真全自动引擎（详细设计）

### 数据模型变更
- `tenants.config_json` 增加字段：
  ```json
  {
    "auto_send_enabled": true,
    "high_risk_block": true,
    "quota_per_day": 100,
    "pause_until": null,
    "boss_phone_webhook": "https://...",
  }
  ```

### 新模块 `server/auto_send.py`
```python
class AutoSendDecider:
    async def decide(self, suggestion, tenant, health_score) -> AutoSendDecision:
        # decision: "auto_send" | "blocked_high_risk" | "blocked_paused" | "blocked_unhealthy" | "review_required"
        ...

    async def trigger_send(self, suggestion) -> None:
        # 通过 ws_manager 把指令推给 client.sender
        ...

    async def notify_boss(self, tenant, suggestion, reason) -> None:
        # 推老板手机（飞书/微信小助手 webhook · 先 mock）
        ...
```

### main.py /v1/inbound 集成点
- `inbound()` 末尾不再只 push WS（review）· 走 `AutoSendDecider.decide`
- 新增 `POST /v1/control/{tenant_id}/pause` · `POST /v1/control/{tenant_id}/resume`

---

## 三、F2 · 客户档案引擎

### Schema
```sql
CREATE TABLE customer_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    nickname TEXT,                    -- 客户昵称（自动从消息中提）
    preferred_addressing TEXT,        -- 称呼偏好：亲/宝/老师/X 总
    vip_tier TEXT DEFAULT 'C',        -- A/B/C
    purchase_history TEXT,            -- JSON: [{date, sku, amount}]
    sensitive_topics TEXT,            -- JSON: ["价格敏感", "对甲醛过敏"]
    tags TEXT,                        -- JSON: ["微商代理", "老顾客"]
    last_intent TEXT,
    last_emotion TEXT,
    last_message_at INTEGER,
    total_messages INTEGER DEFAULT 0,
    accepted_replies INTEGER DEFAULT 0,
    notes TEXT,                       -- 老板手动备注
    updated_at INTEGER NOT NULL,
    UNIQUE(tenant_id, chat_id)
);
CREATE INDEX idx_customer_tenant ON customer_profiles(tenant_id);
CREATE INDEX idx_customer_lastmsg ON customer_profiles(tenant_id, last_message_at DESC);
```

### 新模块 `server/customer_profile.py`
```python
class CustomerProfileEngine:
    async def get_or_create(self, tenant_id, chat_id, sender_name) -> CustomerProfile
    async def update_after_inbound(self, profile, msg, intent) -> None
    async def update_after_send(self, profile, suggestion, decision) -> None
    async def render_for_prompt(self, profile) -> str  # 给 prompt_builder 用
    async def compute_vip_tier(self, profile) -> str   # A/B/C
```

### prompt_builder 集成
```python
# build_system_prompt 新增参数 customer_profile
SYSTEM_PROMPT_TEMPLATE = """...
# 客户档案（已知信息）
{customer_profile_block}
..."""
```

`render_for_prompt` 例子：
```
【客户档案】
- 称呼：王姐（VIP-A）
- 上次购买：2026-03 · 玉兰油精华 · ¥299
- 偏好：怕油腻 · 喜欢轻薄质地
- 备注：女儿 5 岁 · 偶尔问儿童面霜
```

---

## 四、F3 · 知识库 RAG

### Schema
```sql
CREATE TABLE knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    source TEXT NOT NULL,            -- "products.md" | "price_list.csv"
    chunk_text TEXT NOT NULL,
    embedding TEXT NOT NULL,         -- JSON list[float] · 384 维
    tags TEXT,                       -- JSON
    created_at INTEGER NOT NULL
);
CREATE INDEX idx_knowledge_tenant ON knowledge_chunks(tenant_id);
```

### 模块 `server/knowledge_base.py`
```python
class KnowledgeBase:
    def __init__(self, embedder=None):
        self.embedder = embedder or BGEEmbedder("BAAI/bge-small-zh-v1.5")

    async def ingest(self, tenant_id, source, text, chunk_size=300) -> int
    async def query(self, tenant_id, query_text, top_k=3) -> list[Chunk]
    async def delete_source(self, tenant_id, source) -> int
```

### embedder 选型
- `sentence-transformers/BAAI/bge-small-zh-v1.5` · 384 维 · ~100MB
- 首次启动延迟下载 · 缓存到 `~/.cache/huggingface/`
- macOS M4 Pro 推理 50ms/chunk
- **fallback**：环境变量 `BAIYANG_EMBEDDER_MOCK=true` → 用 hash 作为伪 embedding（仅测试）

### Chunk 切分
- 按 `\n\n` 分段 · 段超 300 字按句号再切
- markdown 表格保留完整一行
- CSV 每行作为一个 chunk

### 召回算法
- numpy cosine 全表扫（早期 < 1000 chunk · 性能足够）
- Phase 2 升 pgvector

### prompt_builder 集成
```
# 知识库参考（top 3 相关条目）
{knowledge_block}
```

---

## 五、F4 · 跟进序列引擎

### Schema
```sql
CREATE TABLE follow_up_tasks (
    task_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    sender_name TEXT,
    task_type TEXT NOT NULL,         -- "unpaid_30min" | "paid_1day" | "satisfaction_7d" | "repurchase_30d"
    scheduled_at INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending | sent | cancelled | failed
    template_id TEXT,
    context_json TEXT,               -- JSON: 触发时的上下文
    created_at INTEGER NOT NULL,
    sent_at INTEGER
);
CREATE INDEX idx_followup_due ON follow_up_tasks(status, scheduled_at);
CREATE INDEX idx_followup_tenant ON follow_up_tasks(tenant_id, status);
```

### 模块 `server/follow_up.py`
```python
class FollowUpEngine:
    TYPE_DELAYS = {
        "unpaid_30min":   30 * 60,
        "paid_1day":      86400,
        "satisfaction_7d": 7 * 86400,
        "repurchase_30d": 30 * 86400,
    }

    async def schedule(self, tenant_id, chat_id, task_type, context) -> str
    async def cancel(self, task_id) -> bool
    async def tick(self) -> int  # APScheduler 每分钟调一次

class FollowUpTemplates:
    UNPAID_30MIN = "亲，刚才那个订单看您还没付款～有什么疑问可以问我哦"
    PAID_1DAY = "亲，包裹到了么？有任何问题随时找我～"
    SATISFACTION_7D = "您好，上次的产品用了一周感觉怎么样呀？"
    REPURCHASE_30D = "好久不见～我们这边新到了一批，您之前买的那款现在有 9 折哦"
```

### 触发集成（generator 后处理）
```python
# server/main.py /v1/inbound 末尾
if intent.intent == IntentEnum.ORDER:
    asyncio.create_task(
        follow_up_engine.schedule(
            tenant_id, chat_id, "unpaid_30min",
            context={"original_msg": msg.text}
        )
    )
```

### tick 逻辑
- 每分钟扫 `WHERE status='pending' AND scheduled_at <= now()`
- 每条 task 调 generator 生成跟进文案 → AutoSendDecider 走全自动流程
- 失败重试 3 次 · 仍失败 → status='failed' + audit log

---

## 六、F5 · 意图升级

### 新枚举 `shared/types.py`
```python
class EmotionEnum(str, Enum):
    CALM = "calm"
    ANXIOUS = "anxious"   # 急 · 反复问
    ANGRY = "angry"        # 不爽 · 投诉
    EXCITED = "excited"    # 兴奋 · 临门成交信号
```

### proto.py
```python
class IntentResult(BaseModel):
    intent: IntentEnum
    emotion: EmotionEnum = EmotionEnum.CALM    # ← 新增
    confidence: float
    risk: RiskEnum
    matched_keywords: list[str] = []
```

### classifier.py 升级
```python
class IntentClassifier:
    def __init__(self, mode="hybrid", llm_client=None):
        self.mode = mode
        self.llm_client = llm_client

    async def classify(self, text, history=None) -> IntentResult:
        rule_result = self._classify_rule(text)
        if self.mode == "rule":
            return rule_result
        if self.mode == "hybrid" and rule_result.confidence >= 0.6:
            # 规则置信度高 · 用规则结果 · 但仍补 emotion
            rule_result.emotion = self._guess_emotion_rule(text)
            return rule_result
        # mode == llm 或 hybrid 低置信度 → LLM
        return await self._classify_llm(text, history)

    async def _classify_llm(self, text, history) -> IntentResult:
        # JSON-mode prompt: 让 LLM 同时返回 intent + emotion + risk
        ...
```

### 情绪规则（fast path）
| 关键词/特征 | emotion |
|---|---|
| "急" "马上" "等不及" "?" 数 ≥3 | ANXIOUS |
| "差评" "投诉" "退货" "骗" "气" | ANGRY |
| "好的!!" "买买买" "现在就要" 字数 ≤8 + 感叹号 | EXCITED |
| 其他 | CALM |

### prompt_builder 集成
```python
EMOTION_BLOCKS = {
    EmotionEnum.ANGRY: "客户不爽。请共情 + 软化语气 · 不解释 · 主动认错 · 引导转人工",
    EmotionEnum.ANXIOUS: "客户急。请简短直接 · 立即给确定性答复",
    EmotionEnum.EXCITED: "客户兴奋。临门一脚 · 可推优惠/限时/赠品 · 帮他下决心",
    EmotionEnum.CALM: "客户平静。自然温暖回复",
}
```

---

## 七、F6 · 反封号引擎

### Schema
```sql
CREATE TABLE account_health_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,        -- 微信账号标识
    metric_name TEXT NOT NULL,       -- "friend_pass_rate" | "msg_similarity_avg" | "reply_rate" | "ip_switches" | "heartbeat_anomaly"
    value REAL NOT NULL,
    recorded_at INTEGER NOT NULL
);
CREATE INDEX idx_health_tenant ON account_health_metrics(tenant_id, account_id, recorded_at DESC);

CREATE TABLE account_health_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    score REAL NOT NULL,             -- 0-100
    level TEXT NOT NULL,             -- "green" | "yellow" | "red"
    daily_quota_override INTEGER,
    paused_until INTEGER,
    last_evaluated_at INTEGER NOT NULL,
    UNIQUE(tenant_id, account_id)
);
```

### 5 维度 + 评分公式
```python
WEIGHTS = {
    "friend_pass_rate":  25,   # 好友通过率 · 0.85+ 满分
    "msg_similarity_avg": 25,  # 消息相似度均值 · ≤0.6 满分
    "reply_rate":        20,   # 客户回复率 · ≥0.4 满分
    "ip_switches":       15,   # IP 切换次数 · 0 满分 · 每多 1 次扣 5
    "heartbeat_anomaly": 15,   # 心跳异常 · 0 满分
}

def score_metric(name, value):
    if name == "friend_pass_rate":   return min(100, value / 0.85 * 100)
    if name == "msg_similarity_avg": return max(0, (1 - value / 0.6) * 100)
    if name == "reply_rate":         return min(100, value / 0.4 * 100)
    if name == "ip_switches":        return max(0, 100 - value * 20)
    if name == "heartbeat_anomaly":  return max(0, 100 - value * 25)
    return 50

def composite_score(metrics: dict) -> float:
    return sum(WEIGHTS[k] * score_metric(k, v) / 100 for k, v in metrics.items())

def health_level(score: float) -> str:
    return "green" if score >= 80 else "yellow" if score >= 60 else "red"
```

### 自动响应
| level | 动作 |
|---|---|
| green ≥80 | 正常 · daily_quota = config |
| yellow 60-80 | daily_quota 砍半 · sender 间隔 ×2 · 飞书通知 |
| red <60 | 暂停 1 小时 · paused_until = now + 3600 · 飞书报警 + 触发 F7 容灾 |

### 模块 `server/health_monitor.py`
```python
class HealthMonitor:
    async def record(self, tenant_id, account_id, metric_name, value)
    async def evaluate(self, tenant_id, account_id) -> AccountHealthStatus
    async def tick_all(self) -> int  # APScheduler 每 5 分钟
    async def get_status(self, tenant_id, account_id) -> AccountHealthStatus
    async def manual_recover(self, tenant_id, account_id) -> bool
```

---

## 八、F7 · 多账号容灾

### Schema 变更
- `tenants.config_json` 增加 accounts 字段：
  ```json
  {
    "accounts": [
      {"account_id": "primary_wx_001", "role": "primary", "wxid": "wxid_xxx"},
      {"account_id": "secondary_wx_002", "role": "secondary", "wxid": "wxid_yyy"}
    ],
    "active_account_id": "primary_wx_001"
  }
  ```

### 新表
```sql
CREATE TABLE account_failover_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    from_account TEXT NOT NULL,
    to_account TEXT NOT NULL,
    reason TEXT NOT NULL,
    triggered_at INTEGER NOT NULL,
    auto BOOLEAN NOT NULL DEFAULT 1
);
```

### 模块 `server/account_failover.py`
```python
class AccountFailover:
    async def get_active(self, tenant_id) -> Account
    async def list_all(self, tenant_id) -> list[Account]
    async def auto_failover(self, tenant_id, reason) -> Optional[Account]
        # 选下一个 health.level == green 的 secondary
    async def manual_switch(self, tenant_id, target_account_id) -> Account
```

### 触发集成
- health_monitor 红灯 → 异步调 `auto_failover`
- AutoSendDecider 用 `failover.get_active(tenant_id)` 决定推到哪个 client

---

## 九、F8 · Dashboard 升级

### 新接口
- `GET /v1/dashboard/{tenant_id}/v2` 返回升级版 JSON
- `GET /v1/dashboard/{tenant_id}/trend?days=7` 趋势数据
- `GET /v1/dashboard/{tenant_id}/customers?tier=A` 客户分级
- `GET /v1/dashboard/{tenant_id}/funnel` 成交漏斗
- `GET /v1/dashboard/{tenant_id}/benchmark` 同行对标
- `POST /v1/dashboard/{tenant_id}/weekly_report/send` 手动触发周报

### 新 Dashboard JSON shape
```json
{
  "tenant_id": "...",
  "as_of": 1234567890,
  "today": {...同前},
  "week_trend": {
    "dates": ["2026-04-10", ...],
    "acceptance_rate": [0.83, 0.85, ...],
    "sent_count": [42, 51, ...],
    "high_risk_blocked": [2, 1, ...]
  },
  "customers": {
    "total": 156,
    "tier_a": 12,
    "tier_b": 48,
    "tier_c": 96,
    "stale_30d_alert": ["chat_id_xxx", ...]
  },
  "funnel": {
    "inquiry": 89,
    "negotiation": 51,
    "order": 18,
    "repurchase": 7,
    "rates": {"inq_to_neg": 0.57, "neg_to_order": 0.35, "order_to_rep": 0.39}
  },
  "benchmark": {
    "industry": "微商",
    "your_acceptance_rate": 0.83,
    "industry_p50": 0.65,
    "industry_p90": 0.85,
    "delta_pct": 27.7
  },
  "health": {
    "primary_account_score": 92,
    "active_account_id": "primary_wx_001",
    "yellow_alerts": 0,
    "red_alerts": 0
  }
}
```

### 新模板 `server/templates/dashboard.html`
- chart.js CDN 画 7 天趋势线
- 客户分级 3 个卡片 + 沉睡客户列表
- 成交漏斗（横向 funnel chart）
- 同行对标 progress bar

### 周报推送
- `evolution/weekly_report.py`（不放 evolution 的话放 `server/weekly_report.py`）
- 渲染 markdown · 调飞书 webhook（先 mock）

---

## 十、清理动作详细设计

### C1 · llm_client.py
- 新建 `server/llm_client.py` · 复制 `hermes_bridge.py` 内容 · 类名 `HermesBridge` → `LLMClient`
- `HermesBridge` 改成 backward-compat alias：`HermesBridge = LLMClient`
- 新代码只 import `LLMClient` · 旧测试不用改
- 注释顶部说明：原 hermes_bridge 历史命名 · 已重构为纯 LLM 客户端

### C2 · training_queue.py
```python
# evolution/training_queue.py
class TrainingQueue:
    """采纳/编辑/拒绝 → 训练数据队列。Phase 2 LoRA 训练时全量导出。"""

    async def append(self, tenant_id, suggestion, review) -> None
    async def export(self, tenant_id, since=None) -> Path  # 写 jsonl
    async def stats(self, tenant_id) -> dict
```

Schema：
```sql
CREATE TABLE training_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id TEXT NOT NULL,
    customer_msg TEXT NOT NULL,
    ai_reply TEXT NOT NULL,
    final_text TEXT NOT NULL,        -- accept = ai_reply, edit = edited_text
    decision TEXT NOT NULL,
    intent TEXT,
    emotion TEXT,
    weight REAL NOT NULL DEFAULT 1.0,  -- accept=1.0 / edit=0.7 / reject=-0.5
    created_at INTEGER NOT NULL
);
```

`evolution/industry_flywheel.py` → 删除（含测试 `tests/test_industry_flywheel.py` → 改成 `tests/test_training_queue.py`）

### C3 · MISSION.md v2
- 删 §1 §10 §13 §15（白羊立宪 / 师徒契约 / 立宪签字 / 修订历史中跟童虎/紫龙相关的部分）
- 改 §1：纯产品定位
- 改 §2 §3 §4 §5 §6 §7：保留（已经是产品语言）
- 删 §8（STELLA + AutoMaAS + Alignment Check）
- 改 §9：删"白羊"自我宣读 · 改"产品自检"
- 加 §16：全自动 + 副驾驶外壳的明文宪法

### C4 · ARCHITECTURE.md v2
- 删 hermes-agent:8317 + 紫龙 references
- 数据流图按全自动直发流程重画（见本文 §一）
- 8 个模块拓扑图
- 新表清单（customer_profiles / knowledge_chunks / follow_up_tasks / health_metrics / accounts / training_queue）

### C5 · wechat_agent/CLAUDE.md
- 项目背景 + 核心定位 + 关键路径
- 与 ~/CLAUDE.md（whale_tracker）解耦的注释

### C6 · review_popup.py
- 添加 `mode='auto'` 选项 · 默认不弹
- 仅 `tenants.config.auto_send_enabled=False` 或 `risk=high` 时弹

---

## 十一、依赖图（执行顺序）

```
                ┌── F2 客户档案 ──┐
                │                 │
C1 llm_client → │── F3 知识库 RAG ─┼─→ F1 全自动引擎 ─┐
                │                 │                  │
                │── F5 意图+情绪──┘                  │
                │                                    ├─→ F4 跟进序列
                │                                    │
                ├── F6 反封号 ────────────────────── │
                │                                    │
                └── F7 多账号容灾 ────────────────── │
                                                     │
C2 training_queue ──────────────── 接 F1 后处理 ────┘

文档清理（与代码并行 · 可派 Sonnet subagent）：
C3 MISSION v2  C4 ARCHITECTURE v2  C5 CLAUDE.md  F8 Dashboard 升级
```

### 并行批次
- **批次 A · 0-2 天**：C1 + F2 + F3 + F5 +（subagent 并行：C3 + C4 + C5）
- **批次 B · 2-5 天**：F1 + C2 + F6 +（subagent 并行：F8）
- **批次 C · 5-9 天**：F4 + F7 + 集成测试
- **批次 D · 9-11 天**：端到端真路径测试 · 6 场景 + 修 bug

---

## 十二、测试策略

### 单测（每个模块独立）
- F1: test_auto_send.py（10+ 用例）
- F2: test_customer_profile.py（8+）
- F3: test_knowledge_base.py（10+ · 含 mock embedder）
- F4: test_follow_up.py（8+）
- F5: test_classifier_hybrid.py（12+ 含情绪）
- F6: test_health_monitor.py（10+ · 5 维度边界）
- F7: test_account_failover.py（6+）
- F8: test_dashboard_v2.py（8+）
- C2: test_training_queue.py（6+）

### 端到端真路径（6 场景）
1. 陌生新客首次询价 → AI 答 → 自动发 → 创建 customer_profile
2. 老客复购 → AI 引用历史 → 自动发 → 更新 profile
3. 客户砍价 → emotion=NEGOTIATION + EXCITED → 临门推优惠
4. 客户投诉 → emotion=ANGRY + risk=HIGH → 熔断不发 · 推老板通知
5. 客户下单 → 自动发"亲，已记下" → 30 分钟后自动催付款
6. 长尾询价 → RAG 召回产品参数 → 准确报价

每个场景跑完后断言：DB 状态正确 + audit log 完整 + WS 推送成功。

### 反封号压测
- 模拟 1000 条消息 · 高相似度 30% → health_score 下降 → 自动降速
- 模拟 IP 切换 5 次 → 红灯 → 触发 failover
- 验证：不会卡死 · 不会误降 · failover 不丢消息

---

## 十三、回归保护

- 现有 149 测试不动 · First Wave 新增 ≥40 测试 · 总 ≥189
- 关键回归：
  - inbound 流程兼容（review_popup 默认关后老路径仍能跑）
  - prompt_builder 14 硬约束不破坏
  - hermes_bridge 别名仍工作（旧测试不改）

---

## 十四、性能预算

| 路径 | 预算 |
|---|---|
| /v1/inbound 端到端 P95 | < 2.5s（含 LLM 调用） |
| RAG 召回 (top 3) | < 100ms |
| 客户档案查询 | < 30ms |
| health_monitor.tick_all (10 tenant) | < 500ms |
| follow_up.tick (1000 task) | < 200ms |
| Dashboard /v2 P95 | < 300ms |
