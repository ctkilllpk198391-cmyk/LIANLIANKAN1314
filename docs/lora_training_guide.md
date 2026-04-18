# LoRA 训练操作手册

> 给连大哥（或未来训练运维）的 GPU 训练操作指南
> 当 0 号客户（连大哥）数据攒到 ≥1000 配对时执行
> 单卡 12-24GB GPU 即可 · A100 80G 最佳

---

## 一、前置准备

### 1.1 硬件
- NVIDIA GPU 12GB+（推荐 A100 80G · 也可 RTX 4090 24GB · 最低 RTX 3060 12GB）
- 50GB 磁盘（base model + LoRA + checkpoint）
- 32GB RAM

### 1.2 软件
```bash
# 装 CUDA / PyTorch（按 GPU 选）
pip install torch==2.5.0+cu121 --index-url https://download.pytorch.org/whl/cu121

# 装 LLaMA-Factory
git clone https://github.com/hiyouga/LLaMA-Factory ~/LLaMA-Factory
cd ~/LLaMA-Factory && pip install -e ".[torch,metrics]"

# 装 Unsloth 加速
pip install "unsloth @ git+https://github.com/unslothai/unsloth.git"
```

### 1.3 下载 base model
```bash
# Qwen3-8B-Instruct (~16GB)
huggingface-cli download Qwen/Qwen3-8B-Instruct --local-dir models/Qwen3-8B-Instruct
```

---

## 二、训练流程（5 步）

### Step 1 · 数据采集（客户端做）
客户端解析 WeChatMsg 导出 → `data/tenant/tenant_0001/train_chatml.jsonl`

### Step 2 · 验证数据
```bash
cd ~/wechat_agent
.venv/bin/python -c "
from pathlib import Path
import json
p = Path('data/tenant/tenant_0001/train_chatml.jsonl')
lines = p.read_text(encoding='utf-8').splitlines()
print(f'样本数: {len(lines)}')
print(f'第一条: {json.loads(lines[0])}')
"
```

### Step 3 · 生成训练配置
```bash
.venv/bin/python -c "
from pipeline.train_lora import LoRAConfig, write_training_config
from pathlib import Path

cfg = LoRAConfig(tenant_id='tenant_0001')
write_training_config(cfg, Path('configs/train_tenant_0001.yaml'))
"
```

### Step 4 · 启动训练
```bash
# 方法 A：直接 CLI（手动）
cd ~/LLaMA-Factory
llamafactory-cli train ~/wechat_agent/configs/train_tenant_0001.yaml

# 方法 B：用白羊 launcher（自动 OOM fallback）
cd ~/wechat_agent
.venv/bin/python -c "
import asyncio
from pathlib import Path
from pipeline.train_lora import LoRAConfig, TrainingLauncher, train_with_oom_fallback

async def main():
    cfg = LoRAConfig(tenant_id='tenant_0001')
    launcher = TrainingLauncher()
    state = await train_with_oom_fallback(
        cfg,
        Path('configs/train_tenant_0001.yaml'),
        launcher,
        log_callback=lambda line: print(line),
    )
    print(f'训练完成 · loss={state.last_loss} · steps={state.step} · oom={state.oom}')

asyncio.run(main())
"
```

### Step 5 · 评估
```bash
.venv/bin/python -c "
import asyncio
from pipeline.judge import JudgeLLM, EvalReportRow, render_eval_report
from server.hermes_bridge import HermesBridge

async def main():
    judge = JudgeLLM(HermesBridge(mock=False))
    # 30 条 holdout 数据 · 调真模型对比
    rows = []
    # ... 加载 30 条样本逐一调 LoRA 推理 + judge.judge
    md = render_eval_report('tenant_0001', rows)
    Path('reports/tenant_0001_eval.md').write_text(md, encoding='utf-8')

asyncio.run(main())
"
```

---

## 三、常见问题

### Q1: OOM 怎么办？
A: `make_oom_fallback()` 自动降配 · batch_size /2 · grad_accum *2 · max_seq /2。
手动调：`LoRAConfig(batch_size=2, grad_accum=8, max_seq_length=1024)`

### Q2: loss 不降怎么办？
A: 检查：
- 数据质量（去敏后是否有空 reply）
- learning_rate 太大/太小（默认 2e-4 · 试 1e-4 / 5e-5）
- 数据量太少（< 500 → 等攒够再训）

### Q3: 训完风格不像怎么办？
A: 检查：
- 训练数据是否来自老板本人（grep isSender=1）
- 训练 epoch（默认 3 · 试 5）
- LoRA rank 调大（默认 16 · 试 32 · 64）

### Q4: 训练时间太长？
A:
- 用 Unsloth（默认开）
- 用 4-bit QLoRA（默认开）
- 数据量 1000 条 · 单卡 A100 应 < 1h

---

## 四、训练后部署

```bash
# LoRA 文件位置
ls models/tenant_0001/lora/
# adapter_model.safetensors  adapter_config.json

# 注册到 router（Phase 1 单 LoRA）
.venv/bin/python -c "
from server.model_router import ModelRouter
r = ModelRouter()
r.mark_lora_ready('tenant_0001')
print('LoRA tenant_0001 已注册')
"

# Phase 3 vLLM 多 LoRA 部署
vllm serve ./models/Qwen3-8B-Instruct \
  --enable-lora \
  --max-loras 100 \
  --lora-modules tenant_0001=./models/tenant_0001/lora
```

---

## 五、定时增量训练（Phase 2 末期）

### 5.1 systemd timer
```ini
# /etc/systemd/system/baiyang-train.timer
[Unit]
Description=Daily LoRA incremental training

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

### 5.2 service
```ini
# /etc/systemd/system/baiyang-train.service
[Service]
Type=oneshot
WorkingDirectory=/opt/baiyang/wechat_agent
ExecStart=/opt/baiyang/.venv/bin/python -m pipeline.daily_train
```

### 5.3 daily_train.py（Phase 2 末实现）
- 拉今日 reviews（accept/edit/reject）
- 生成 DPO 配对
- 跑 DPO 训练 10-30 分钟
- 灰度 20% 流量 24h
- 不降 → 全量替换

---

## 六、故障定位 cheatsheet

| 现象 | 排查 |
|---|---|
| LoRA 文件 0 字节 | OOM 中断 · 看 nvidia-smi · 试 fallback |
| llamafactory-cli 找不到 | `which llamafactory-cli` · 加 PATH |
| 推理 0.1 tok/s | 没用 fp16/4bit · 检查 quantization_bit=4 |
| LoRA 风格漂 | 训练数据混了非老板回复 · grep isSender |
