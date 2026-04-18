# Phase 2 · LoRA 训练管线 · Design

> Spec ID：`phase2_lora_training`
> 起草日期：2026-04-15

---

## 1. 总览

```
┌─────────── 客户端（Windows）───────────┐
│  WeChatMsg 导出 sqlite (本人授权)      │
│         │                              │
│  pipeline.extract_chat                 │
│  ├─ parse sqlite                       │
│  ├─ pair (customer_msg, boss_reply)    │
│  ├─ desensitize（手机/卡号）          │
│  ├─ filter（长度/噪音/重复）          │
│  └─ output train.jsonl                 │
│         │ 加密上传                     │
└─────────┼──────────────────────────────┘
          ▼
┌─────────── 服务端（GPU）───────────────┐
│  pipeline.train_lora                   │
│  ├─ 生成 LLaMA-Factory yaml            │
│  ├─ subprocess 启动训练                │
│  ├─ 监控进度（tail loss）              │
│  └─ 产出 models/{tenant}/lora.safetensors│
│         │                              │
│  pipeline.judge                        │
│  ├─ 30 条 holdout 样本                 │
│  ├─ judge LLM (DeepSeek-R1) 打分       │
│  └─ 报告 markdown                      │
│         │                              │
│  pipeline.dpo_pair (定期)              │
│  ├─ reviews 表 → chosen/rejected      │
│  └─ output dpo.jsonl                   │
│         │                              │
│  server.model_router                   │
│  └─ mark_lora_ready(tenant_id)         │
└────────────────────────────────────────┘
```

---

## 2. 数据流细节

### 2.1 WeChatMsg sqlite 结构（参考开源项目）

```sql
-- 微信本地 MSG.db schema（脱敏后简化版）
CREATE TABLE MSG (
    localId INTEGER PRIMARY KEY,
    talkerWxid TEXT,         -- 对话方
    isSender INTEGER,        -- 0=对方发, 1=我发
    type INTEGER,            -- 1=text, 3=image, 34=voice, ...
    content TEXT,
    createTime INTEGER       -- unix ts
);
```

### 2.2 配对算法

```python
def pair_messages(rows: list[Row]) -> list[TrainingPair]:
    """按时间顺序遍历 · 每一对 (对方→我发) 算一个配对。

    规则：
    - 跳过 type != 1 的消息（图/语/卡）
    - 老板（isSender=1）的回复必须紧跟在客户（isSender=0）的消息后
    - 5 分钟内的多条客户消息合并为一条（context）
    - 5 分钟内老板的多条回复合并为一条（reply）
    """
    pairs = []
    pending_customer: list[str] = []
    last_customer_ts = 0

    for row in rows:
        if row.type != 1:
            continue
        if row.isSender == 0:
            if pending_customer and row.createTime - last_customer_ts > 300:
                pending_customer = []
            pending_customer.append(row.content)
            last_customer_ts = row.createTime
        else:
            if not pending_customer:
                continue
            pairs.append(TrainingPair(
                customer_msg="\n".join(pending_customer),
                boss_reply=row.content,
                chat_name=row.talkerWxid,
                timestamp=row.createTime,
                raw_context=pending_customer.copy(),
            ))
            pending_customer = []

    return pairs
```

### 2.3 去敏规则

```python
DESENSITIZE_PATTERNS = [
    (r"1[3-9]\d{9}",                       "[手机]"),
    (r"\b\d{15,19}\b",                     "[卡号]"),
    (r"\b\d{17}[\dxX]\b",                  "[身份证]"),
    (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[邮箱]"),
    (r"https?://\S+",                       "[链接]"),
]
```

### 2.4 噪音过滤

```python
NOISE_PATTERNS = {
    "纯 emoji": r"^[\U0001F300-\U0001FAFF\u2600-\u27BF]+$",
    "纯标点": r"^[\W_]+$",
    "纯叠字": ["哈哈", "呵呵", "嗯嗯", "好的", "知道了", "ok", "okay"],
}

MIN_REPLY_LEN = 10
MAX_REPLY_LEN = 300
```

---

## 3. 训练管线

### 3.1 LLaMA-Factory yaml（pipeline.train_lora 自动生成）

```yaml
model_name_or_path: Qwen/Qwen3-8B-Instruct
stage: sft
do_train: true
finetuning_type: lora
lora_target: all
lora_rank: 16
lora_alpha: 32
lora_dropout: 0.05
dataset: tenant_0001
dataset_dir: ./data/tenant/tenant_0001
template: qwen
cutoff_len: 2048
max_samples: 50000
output_dir: ./models/tenant_0001/lora
logging_steps: 10
save_steps: 100
warmup_steps: 50
learning_rate: 2.0e-04
num_train_epochs: 3
per_device_train_batch_size: 4
gradient_accumulation_steps: 4
lr_scheduler_type: cosine
quantization_bit: 4
use_unsloth: true
fp16: true
```

### 3.2 训练启动器

```python
class TrainingLauncher:
    def __init__(self, llama_factory_path: Path):
        self.lf_path = llama_factory_path  # LLaMA-Factory 仓库本地路径

    async def launch(self, config_yaml: Path, log_callback=None) -> int:
        """subprocess 启动 · stream loss 到 log_callback。"""
        cmd = ["llamafactory-cli", "train", str(config_yaml)]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for line in proc.stdout:
            text = line.decode("utf-8", errors="replace")
            if log_callback:
                await log_callback(text)
        return await proc.wait()
```

### 3.3 训练监控

- 每 10 step 解析 `loss=X.XX` 写入 `models/{tenant}/training.log`
- loss 连续 50 step 不降 → 早停
- OOM → fallback 配置（batch=2, accum=8, max_seq=1024）

---

## 4. 评估管线

### 4.1 judge LLM 接口

```python
class JudgeLLM:
    """调 DeepSeek-R1 / Claude Sonnet 当评委。"""

    async def judge(self, customer_msg: str, boss_real: str, ai_generated: str) -> dict:
        """返回 {style_match: 0-1, naturalness: 0-1, on_topic: 0-1, comment: str}。"""
        prompt = f"""
你是一个微信聊天风格评委。给定客户消息和两条回复（一条是老板真实回复，一条是 AI 生成），
判断 AI 生成的回复是否符合老板的风格、自然度、话题相关性。

客户消息: {customer_msg}
老板真实回复: {boss_real}
AI 生成回复: {ai_generated}

输出 JSON: {{"style_match": 0-1, "naturalness": 0-1, "on_topic": 0-1, "comment": "..."}}
        """
        # 调 hermes_bridge.respond → 解析 JSON
```

### 4.2 评估报告

```markdown
# tenant_0001 LoRA 评估报告 (2026-04-15)

## 数据集
- 训练样本: 1234
- 评估样本: 30 (holdout)

## 主要指标
| 指标 | 值 | 目标 |
|---|---|---|
| 风格相似度 | 0.67 | ≥ 0.5 ✅ |
| 自然度 | 0.81 | ≥ 0.7 ✅ |
| 话题相关 | 0.92 | ≥ 0.8 ✅ |
| 禁用词命中率 | 0.0% | ≤ 1% ✅ |
| 超长率 | 0.0% | ≤ 1% ✅ |

## 失败案例 (Top 3)
1. ...
2. ...
```

---

## 5. DPO 配对

### 5.1 数据来源
- `reviews.decision == "edit"` 的样本：`chosen = edited_text`, `rejected = sug.text`
- `reviews.decision == "reject"` 的样本：需要从其他 accepted 配对找 chosen

### 5.2 触发条件
- DPO 配对量 >= 50
- 距离上次 SFT >= 7 天
- 距离上次 DPO >= 3 天

---

## 6. 部署整合

### 6.1 训完后注册到 model_router

```python
# pipeline 训练完成后调用
from server.model_router import ModelRouter

router = ModelRouter()
router.mark_lora_ready("tenant_0001")
# 后续 inbound 走 lora:tenant_0001 而非 hermes_default
```

### 6.2 vLLM 多 LoRA 部署（Phase 3）

Phase 2 单 LoRA 用 transformers + peft 加载即可。
Phase 3 客户达 10+ 时，切 vLLM 0.6+ 多 LoRA 热切换。

---

## 7. 测试策略

### 7.1 单元
- `test_extract_chat.py`：mock sqlite → 配对正确性
- `test_desensitize.py`：手机/卡号/邮箱去敏
- `test_train_lora_config.py`：yaml 生成正确
- `test_judge.py`：mock LLM 解析

### 7.2 集成
- `test_pipeline_e2e.py`：mock 数据 → 配对 → 去敏 → 格式转换 → yaml 生成

### 7.3 真实路径（GPU 机器）
- 5 条 mini 数据 → smoke train 1 epoch → 出 LoRA 文件
