# Second Wave (SDW) · Design

> 配套 requirements.md / tasks.md
> 设计原则：第一性原理 · 奥卡姆剃刀 · 复用 First Wave 已有能力

---

## 一、整体集成点

```
inbound msg
    ↓
[ASR] voice_url → 转文字（S5）
    ↓
[VLM] image_url → 描述拼 user prompt（S4）
    ↓
classifier (intent + emotion · 已有)
    ↓
customer_profile · knowledge_base · industry_router (S3) · psych_triggers (S2)
    ↓
prompt_builder (集成 industry_block + psych_block)
    ↓
generator → suggestion
    ↓
anti_detect 处理（S6 · 错别字+变体+疑心检测）
    ↓
cross_sell.maybe_append(S7 · 主动推荐)
    ↓
typing_pacer 算 delay_ms（S1 · 节奏）
message_splitter 拆段（S1 · 多消息）
    ↓
auto_send 决策 + ws push（含 delay_ms 字段）
    ↓
client.sender 等 delay_ms · 分段发

并行后台 jobs（APScheduler · 已有）：
+ 每天 09/14/19 时 moments_manager.tick（S8 朋友圈托管）
```

---

## 二、S1 · 节奏拟人引擎

### 算法
```python
def compute_typing_delay(text: str, base_ms: int = 1500) -> int:
    """高斯分布 · μ 按字数缩放 · σ=0.3μ"""
    n = len(text)
    mu = base_ms + n * 50          # 每字 +50ms
    sigma = mu * 0.3
    delay = max(800, min(8000, int(random.gauss(mu, sigma))))
    return delay

def is_nighttime(now: int) -> bool:
    """00:00-07:00 视为夜间"""
    h = time.localtime(now).tm_hour
    return h < 7
```

### 多消息拆段
```python
def split_messages(text: str, max_per_msg: int = 60) -> list[str]:
    """按 \n / 句号 / ! / ? 切 · 每段 ≤60 字 · 1-3 段"""
    ...
```

### WS payload 加字段
```json
{
  "type": "auto_send_command",
  "msg_id": "...",
  "segments": [
    {"text": "在的 亲~", "delay_ms": 1200},
    {"text": "这款是我们家爆款哦", "delay_ms": 1800},
    {"text": "你想要啥色号？", "delay_ms": 1500}
  ]
}
```

---

## 三、S2 · 心理学触发器引擎

### 6 类触发器枚举
```python
class TriggerType(str, Enum):
    SCARCITY = "scarcity"             # 稀缺：限量/限时
    SOCIAL_PROOF = "social_proof"     # 社会认同：从众
    RECIPROCITY = "reciprocity"       # 互惠：先给价值
    LOSS_AVERSION = "loss_aversion"   # 损失厌恶：不买的代价
    AUTHORITY = "authority"           # 权威：背书
    COMMITMENT = "commitment"         # 承诺一致：复购
```

### 4 维决策表（intent × emotion × stage × vip_tier → trigger）
```python
DECISION_MATRIX = {
    # (intent, emotion, stage) → preferred_triggers
    ("inquiry", "calm", "explore"):       [RECIPROCITY],
    ("inquiry", "anxious", "explore"):    [AUTHORITY, SOCIAL_PROOF],
    ("negotiation", "calm", "compare"):   [SOCIAL_PROOF, AUTHORITY],
    ("negotiation", "excited", "near"):   [SCARCITY, LOSS_AVERSION],
    ("order", "excited", "near"):         [SCARCITY],
    ("chitchat", "calm", "post_buy"):     [COMMITMENT],
    ...
}
```

### 客户阶段识别
```python
def detect_stage(customer_profile, last_intents: list[str]) -> str:
    """explore | compare | near | post_buy | dormant"""
    ...
```

### prompt_builder 集成
新增 `psych_block` 段：
```
# 销售心理触发器（自动选 · 请用此话术）
触发器：稀缺 (scarcity)
模板：今天最后 X 件 / 明天恢复原价 / 限时优惠到 XX 点
要求：
- 给具体数字（不要"很少了"）
- 给截止时间（不要"快了"）
- 用感叹但不滥用（≤2 个 !）
```

---

## 四、S3 · 6 行业模板池

### 文件结构
```
server/industry_templates/
├── 微商.md      （亲~宝~ · 晒单 · 限时）
├── 房产中介.md  （X 总 · 长跟进 · 看房邀约）
├── 医美.md      （神秘感 · 案例图 · 一对一）
├── 教培.md      （共情家长 · 数据 · 案例）
├── 电商.md      （快 · 简洁 · 售后）
└── 保险.md      （顾问感 · 不催 · 规划）
```

### 每行业 markdown 结构
```markdown
# 微商 · 行业 prompt 段

## 称谓
- 男客户：哥 / 老板 / 帅哥
- 女客户：亲 / 宝 / 宝贝 / 姐
- 称呼频率：每 2-3 句一次（不要每句）

## 风格
- 句长：≤30 字 · 短句优先
- 表情：1-2 emoji 每条
- 标点：感叹号慎用 · ~ 多

## 业务关键词
- 库存 / 拼邮 / 包邮 / 拼团 / 反馈
- 禁说："工厂" "代发" "代理" "总代"

## 高频场景应答模板
（10 个常见场景 fallback · 当 LLM 拿不准时用）
```

### industry_router.py
```python
class IndustryRouter:
    def get_prompt_block(self, industry_id: str) -> str:
        """读对应 markdown · cache 内存"""

    async def detect_from_history(self, llm_client, sample_msgs: list[str]) -> str:
        """LLM 看 20 条样本 → 推荐行业 + 风格"""
```

---

## 五、S4 · 图片理解（Qwen3-VL）

### vlm_client.py
```python
class QwenVLClient(BaseLLMClient):
    """阿里云百炼 qwen-vl-max API · OpenAI 兼容协议。"""

    async def describe(self, image_url: str, prompt: str = None) -> str:
        """看图 + 用户问题 → 文字描述。"""
```

### 集成点
- InboundMsg 已有 `msg_type='image'` · 加 `image_url` 字段
- main.py inbound 检测 type=image → 调 vlm.describe → 描述拼 text 前
  - 例：用户发产品图 → 描述："[图片：一瓶玉兰油精华 30ml · 紫色包装]" + 原 text

---

## 六、S5 · 语音转文字

### asr_client.py
```python
class DoubaoASRClient:
    """火山引擎语音识别 · 默认中文。"""

    async def transcribe(self, voice_url: str) -> str:
        """音频 → 文字。"""
```

### 集成点
- InboundMsg 加 `voice_url` 字段
- main.py inbound 检测 type=voice → 调 asr.transcribe → 替换 text 字段后续流程不变

---

## 七、S6 · 反检测套件

### anti_detect.py
```python
TYPO_MAP = {
    "的": "得", "得": "的", "再": "在", "在": "再",
    "做": "作", "作": "做", "你": "您", ...
}

OPENING_VARIANTS = [
    "嗨~", "在的~", "亲在的", "刚看到", "嗯哼", "诶在",
    "看到啦", "亲在呢", "对的~", "好嘞",
]

SUSPICION_PATTERNS = [
    r"你是.*(AI|人工智能|机器人|智能助手|GPT|chatgpt)",
    r"怎么回.*(慢|快)",
    r"(像|是).*(机器|程序|脚本)",
    r"(感觉|怀疑).*(不是真人|是 AI)",
]

def inject_typo(text: str, prob: float = 0.05) -> str: ...
def vary_opening(text: str) -> str: ...
def detect_suspicion(text: str) -> bool: ...
```

### 集成点
- generator.generate 末尾：返 suggestion 前 → anti_detect 处理
- main.py inbound 末尾：detect_suspicion(client_text) → True → audit + notify_boss + 标记 review_required（暂停自动 1 小时）

---

## 八、S7 · 交叉销售引擎

### cross_sell.py
```python
@dataclass
class ProductRec:
    sku: str
    name: str
    reason: str
    score: float

class CrossSellEngine:
    async def recommend(
        self,
        customer_profile: CustomerProfileSnapshot,
        current_intent: IntentEnum,
        knowledge_base: KnowledgeBase,
    ) -> list[ProductRec]:
        """基于历史购买 + 当前意图 + 知识库 · top 1-2 推荐。"""

    async def maybe_append_to_reply(
        self,
        original_reply: str,
        recommendations: list[ProductRec],
    ) -> str:
        """决策：插入到 reply 末尾 / 单独消息 / 不插。"""
```

### 风控
- 每客户每天最多 1 次交叉销售
- 客户当前消息为投诉/差评 → 不推
- 推荐文案要自然（"对了 · 你之前买过 X · 这次新到 Y 也适合你哦"）

---

## 九、S8 · 朋友圈托管

### Schema
```sql
CREATE TABLE moments_posts (
    post_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    post_type TEXT NOT NULL,   -- product/feedback/promo/lifestyle
    content TEXT NOT NULL,
    image_urls TEXT,           -- JSON list
    status TEXT DEFAULT 'draft', -- draft/scheduled/published/cancelled
    scheduled_at INTEGER,
    published_at INTEGER,
    created_at INTEGER NOT NULL
);
```

### moments_manager.py
```python
class MomentsManager:
    POST_PROMPTS = {
        "product":   "晒今天的爆款 · 200 字内 · 要客户视角 · 加 1-2 句行动号召",
        "feedback":  "晒客户反馈截图 + 真情实感感言 · 不假",
        "promo":     "限时活动 · 清楚截止时间 + 优惠内容 · 不夸张",
        "lifestyle": "老板的日常 · 喝咖啡 / 旅行 / 看书 · 真人感",
    }

    async def generate_post(self, tenant_id, post_type) -> str
    async def schedule_daily(self, tenant_id) -> list[str]  # 一天 3 条 · 09/14/19 时
    async def tick(self) -> int  # APScheduler 每小时检查 due posts
```

---

## 十、依赖图（执行顺序）

```
独立批次（强并行）：
├── S1 节奏拟人      ← 我做（涉及核心数据流）
├── S2 心理学触发    ← 我做（涉及 prompt_builder）
├── S6 反检测        ← 我做（generator 末尾集成）
└── S3 行业模板池    ← 派 sonnet（独立 markdown 文件）

依赖 First Wave 模块：
├── S4 图片理解      ← 派 sonnet（独立 vlm_client）
├── S5 语音转文字    ← 派 sonnet（独立 asr_client）
├── S7 交叉销售      ← 派 sonnet（用 customer_profile + knowledge_base）
└── S8 朋友圈托管    ← 派 sonnet（独立 moments_manager + scheduler）

集成（最后做）：
└── main.py 集成 8 件 + 端到端 10 场景测试
```

---

## 十一、测试策略

### 单测（每模块独立）
- S1: test_typing_pacer.py + test_message_splitter.py（≥10）
- S2: test_psych_triggers.py（≥12）
- S3: test_industry_router.py（≥6）
- S4: test_vlm_client.py（≥5 mock）
- S5: test_asr_client.py（≥4 mock）
- S6: test_anti_detect.py（≥10）
- S7: test_cross_sell.py（≥6）
- S8: test_moments.py（≥8）

### 端到端 10 场景
1. 拟人节奏：消息回复延迟 + 多段 · 验证 WS payload 含 segments
2. 心理学：客户砍价 + EXCITED → AI 回复含 scarcity/loss_aversion 关键词
3. 心理学：客户投诉 + ANGRY → AI 回复含 reciprocity（先给价值不推销）
4. 行业适配：tenant=房产 → 称谓"X 总" / tenant=微商 → "亲~"
5. 图片：客户发"这个多少"+ image_url → AI 回带产品参数
6. 语音：客户发 voice_url → AI 转文字 → 正常回复
7. 反检测：客户问"你是 AI 吗" → 暂停自动 + 推老板
8. 反检测：长 reply 含轻微 typo（5% 概率 · 用 fixed seed 验证）
9. 交叉销售：VIP-A 老客户来询价 → 回复含交叉推荐
10. 朋友圈：scheduler 触发 09:00 → 生成 product 类 post → 入 moments_posts 表
