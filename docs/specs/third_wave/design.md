# Third Wave (TDW) · Design

> 配套 requirements.md / tasks.md
> 复用：First Wave (KB/customer_profile/scheduler) + SDW (industry/psych/cross_sell/moments)

---

## 一、整体集成点

```
[T1 客户端] ~/wechat_agent_input/ → watchdog → upload
                ↓
[T1 服务端] /v1/content/upload → content_ingest 多格式解析 → KB 入库
                ↓
[T2] 自动触发 marketing_plan.generate → 朋友圈+SOP+群发草案 → 入 marketing_plans 表
                ↓
[T3] dashboard /v3 → pipeline + actions 计算 → 老板每天看到"今天该跟谁说什么"
                ↓
老板审核 → activate → 进 moments_posts / customer_profile fact / follow_up_tasks
                ↓
所有数据：T4 加密 (per-tenant key + KMS 抽象) → 客户走了带不走
                ↓
T5: 合规导出原始聊天 (csv/json) · 训练资产留 wechat_agent
```

---

## 二、T1 内容摄入引擎

### 客户端 client/content_watcher.py
```python
class ContentWatcher:
    def __init__(self, watch_dir, api_client, tenant_id):
        self.watch_dir = watch_dir or "~/wechat_agent_input/"
        self.api = api_client
        self.tenant = tenant_id

    def start(self):  # watchdog Observer 启动
        ...

    def on_created(self, event):
        # 新文件 → 等 2s（防止半写状态）→ 上传
        ...
```

依赖：`watchdog>=4.0`（macOS dev · Windows prod 都跑得动）

### 服务端 server/content_ingest.py
```python
@dataclass
class ContentRecord:
    file_id: str
    tenant_id: str
    file_name: str
    file_type: str         # md/txt/docx/csv/jpg/png/mp3/mp4
    size_bytes: int
    parsed_chunks: int
    source_tag: str        # 产品/活动/反馈/培训/价格 · LLM 自动分类
    uploaded_at: int

class ContentIngestEngine:
    def __init__(self, kb, vlm, asr, llm_client):
        ...

    async def ingest(self, tenant_id, file_path, file_name, file_bytes) -> ContentRecord:
        """
        路由：
          .md/.txt → 直接 KB.ingest
          .csv → 切行 → KB.ingest
          .docx → python-docx 提文字 → KB.ingest
          .jpg/.png → vlm.describe → KB.ingest
          .mp3/.mp4/.m4a → asr.transcribe → KB.ingest
        分类：LLM 看前 200 字 → 推断 source_tag
        """
        ...

    async def trigger_downstream(self, record):
        """T2 自动生成营销方案（如 source_tag in ['产品', '活动']）"""
        ...
```

### Schema
```sql
CREATE TABLE content_uploads (
    file_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    parsed_chunks INTEGER DEFAULT 0,
    source_tag TEXT,             -- 产品/活动/反馈/培训/价格
    knowledge_chunk_ids TEXT,    -- JSON list[int]
    marketing_plan_id TEXT,      -- 如触发了 T2
    uploaded_at INTEGER NOT NULL
);
```

---

## 三、T2 营销方案生成器

### 数据契约
```python
@dataclass
class MomentPostDraft:
    day_offset: int          # -7 / -3 / 0 / +3
    angle: str               # 悬念/种草/开抢/复盘
    content: str
    suggested_image: str     # 描述（让客户挑图）

@dataclass
class PrivateChatSOP:
    trigger: str             # "客户问活动" / "客户犹豫"
    reply_template: str      # 含变量 {customer_name}

@dataclass
class GroupBroadcast:
    target_tier: str         # A/B/C/all
    text: str
    suggested_send_at: int

@dataclass
class MarketingPlan:
    plan_id: str
    tenant_id: str
    source_content_id: str
    moments_posts: list[MomentPostDraft]
    private_sops: list[PrivateChatSOP]
    group_broadcasts: list[GroupBroadcast]
    estimated_impact: dict   # {expected_orders: int, expected_revenue: float}
    status: str              # draft/active/cancelled
    created_at: int
```

### server/marketing_plan.py
```python
class MarketingPlanGenerator:
    PROMPT_TEMPLATE = """
    基于以下新产品/活动资料 · 生成完整营销方案。
    
    资料内容：{content}
    老板风格：{style_hints}
    行业：{industry}
    历史最佳话术：{best_past_sop}（last 3 month accept_rate top）
    
    输出 JSON：
    {
      "moments_posts": [{ day_offset, angle, content, suggested_image }, ... 5 条],
      "private_sops": [{ trigger, reply_template }, ... 5+ 条],
      "group_broadcasts": [{ target_tier, text, suggested_send_at }, A B C 各一],
      "estimated_impact": { expected_orders, expected_revenue }
    }
    """

    async def generate(self, tenant_id, content_record) -> MarketingPlan: ...
    async def activate(self, plan_id) -> bool: ...
        # → 朋友圈进 moments_posts table (status=scheduled)
        # → 私聊 SOP 写进 tenant.fact / customer_profile.notes
        # → 群发进 follow_up_tasks (各 tier)
```

### Schema
```sql
CREATE TABLE marketing_plans (
    plan_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    source_content_id TEXT,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    activated_at INTEGER,
    created_at INTEGER NOT NULL
);
```

---

## 四、T3 行动型 Dashboard

### server/customer_pipeline.py
```python
@dataclass
class PipelineCustomer:
    chat_id: str
    nickname: str
    vip_tier: str
    stage: str              # SDW S2 阶段 · explore/compare/near/post_buy/dormant
    last_message_at: int
    days_since_last: int
    last_intent: str
    last_emotion: str
    urgency: int            # 0-3 · ⚡ 数量
    pending_value_estimate: float  # ¥ 待成交估值

class CustomerPipelineBuilder:
    async def build(self, tenant_id, max=10) -> list[PipelineCustomer]:
        """SELECT customer_profiles WHERE vip_tier IN (A,B) AND stage IN (NEAR,COMPARE)
        ORDER BY urgency DESC, pending_value DESC LIMIT max"""
```

### server/action_recommender.py
```python
@dataclass
class RecommendedAction:
    chat_id: str
    action_type: str         # care/follow_up/handoff/upsell/repurchase
    reason: str              # 显示给老板看
    suggested_text: str      # AI 草拟话术
    confidence: float

class ActionRecommender:
    async def recommend_for_customer(self, profile) -> Optional[RecommendedAction]:
        """规则引擎：
        - days_since_last >= 30 → care
        - last_intent=inquiry AND days_since_last >= 1 → follow_up
        - last_intent=complaint → handoff
        - vip_tier=A AND days_since_last >= 60 → upsell
        - 上次购买后 30/60/90 天 → repurchase"""
```

### Dashboard v3 接口
- `GET /v1/dashboard/{tenant}/v3` → v2 + pipeline + actions + multi_account_view
- HTML 模板加：
  - 多微信号卡片（每号 health_score + 客户数 + 今日成交）
  - 待成交列表（top 10 · 一键采纳）
  - AI 自动处理摘要（今日 inbound 数 / 自动答数 / 转人工数 / 成交数）
  - 营销方案待审区（latest 3 plans）

---

## 五、T4 数据护城河

### server/encryption.py
```python
class TenantKMS:
    """per-tenant 加密 · 抽象层（dev=fernet · prod=AWS/阿里云 KMS）"""
    
    def __init__(self, backend="fernet", key_dir=None):
        self.backend = backend
        self.key_dir = Path(key_dir or "~/.wechat_agent_keys").expanduser()
        self.key_dir.mkdir(parents=True, exist_ok=True)
        self._cache = {}    # tenant_id → cipher

    def get_or_create_key(self, tenant_id: str) -> bytes:
        """每 tenant 一个 key · 文件存在则读 · 否则生成 + 落盘 (chmod 600)"""

    def encrypt(self, tenant_id: str, plaintext: bytes) -> bytes: ...
    def decrypt(self, tenant_id: str, ciphertext: bytes) -> bytes: ...

    def rotate(self, tenant_id: str): ...  # 留 prod 用

# 用法：
kms = TenantKMS()
encrypted_lora = kms.encrypt(tenant_id, lora_bytes)
# 落盘 → 客户拿走也解不开
```

### 集成点
- `pipeline/train_lora.py` 落盘前 → encrypt
- `server/customer_profile.py` 敏感字段（notes / sensitive_topics）→ encrypt（加 _encrypted 后缀新字段 · backward compat）
- `evolution/training_queue.py` 导出 jsonl 前 → encrypt（仅 export 路径用）

---

## 六、T5 客户授权 + 数据所有权

### legal/data_ownership.md
明文 markdown 协议条款（律师定稿前先草拟）：
1. 用户上传聊天数据归用户所有
2. 训练产生的 LoRA / 客户档案聚合 / embedding 归 wechat_agent
3. 用户可随时申请导出原始聊天（csv/json）· 30 天 grace 后删除
4. 用户离开后训练资产不退还（已写入合同）
5. 数据使用范围：仅用于服务该用户 · 不跨 tenant 共享 · 行业聚合走差分隐私

### server/data_export.py
```python
class DataExporter:
    async def export_chats(self, tenant_id, format="csv") -> bytes:
        """导出原始 messages + suggestions + sent · csv/json
        不导出：customer_profiles / lora / training_queue / knowledge_chunks"""

    async def export_summary(self, tenant_id) -> dict:
        """统计：消息数 / 客户数 / AI 准确率 / 数据保留天数"""
```

### server/data_deletion.py
```python
class DataDeletionManager:
    GRACE_DAYS = 30

    async def request(self, tenant_id, reason="") -> str:
        """记录请求 · 30 天后 cron 真删 · 期间可撤销"""

    async def cancel(self, request_id) -> bool: ...

    async def execute_overdue(self) -> int:
        """每天 03:00 cron · 删超 grace 的请求 · 完整删 messages/profiles/sent/audit
        但保留 training_queue（按协议归 wechat_agent）"""
```

### client/consent_page.py（首装弹窗 · 简化版）
```python
def show_consent_dialog() -> bool:
    """终端打印协议摘要 + 等用户输入 'agree'"""
    print("数据使用授权（必读）")
    print("...")
    return input("输入 'agree' 同意：").strip().lower() == "agree"
```

---

## 七、依赖图（执行顺序）

```
独立批次（强并行）：
├── T1 内容摄入       ← 我做（核心 · 多格式解析）
├── T3 行动 Dashboard ← 派 sonnet（独立）
├── T4 数据护城河     ← 派 sonnet（独立 · cryptography）
└── T5 数据所有权     ← 派 sonnet（独立 · 协议+导出+删除）

依赖 T1：
└── T2 营销方案生成   ← 我做（依赖 T1 content_record 触发）

集成（最后）：
└── main.py 集成 5 件 + e2e 6 场景测试
```

### 并行批次
- 批次 A · Day 0-3 · T1 + T3 + T4 + T5 并行
- 批次 B · Day 3-5 · T2 + 集成
- 批次 C · Day 5-7.5 · e2e + 文档 v6 + 启动验收

---

## 八、测试策略

### 单测
- T1: test_content_ingest.py (≥10 · 各格式 + 分类 + downstream)
- T2: test_marketing_plan.py (≥8 · 生成 + activate + 各 channel)
- T3: test_customer_pipeline.py (≥6) + test_action_recommender.py (≥6)
- T4: test_encryption.py (≥8 · per-tenant key + 加解密)
- T5: test_data_export.py (≥4) + test_data_deletion.py (≥4)

### 端到端 6 场景
1. 魔法文件夹 .md 文件 → KB 召回
2. 魔法文件夹 .csv 价格表 → 询价时 RAG 用
3. 魔法文件夹 "新品发布.md" → 自动生成营销方案 → 老板 activate → 朋友圈入队
4. Dashboard v3 待成交 + 推荐行动
5. 数据导出 csv（仅原始聊天）
6. 数据删除请求 → 30 天 grace 状态
