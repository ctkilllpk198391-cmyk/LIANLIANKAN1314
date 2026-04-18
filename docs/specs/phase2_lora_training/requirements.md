# Phase 2 · LoRA 训练管线 · Requirements

> Spec ID：`phase2_lora_training`
> 阶段：Phase 2（task_plan.md Week 2 Day 8-14）
> 验收人：连大哥
> 起草日期：2026-04-15

---

## 1. 功能范围

把"老板的微信聊天记录" → "老板的数字分身 LoRA 模型" 的完整管线建好。

**0 号客户**：连大哥本人。先把他的 LoRA 训出来，盲测能让 3 个朋友辨认"这是连哥的回复"。

### 1.1 子模块

1. **数据采集**：WeChatMsg 集成 → SQLite 解析 → (客户消息, 老板回复) 配对
2. **数据清洗**：去敏（手机/身份证/银行卡）→ 长度过滤 → 噪音过滤
3. **格式转换**：训练样本对 → ChatML / Alpaca 格式
4. **训练启动**：LLaMA-Factory + Unsloth + QLoRA → 4-bit 量化训练
5. **效果评估**：judge LLM + 人工抽检 + 风格相似度
6. **DPO 配对**：accept vs rewrite 样本对生成
7. **模型部署**：训完的 LoRA 注册到 model_router

---

## 2. 验收标准

### 2.1 数据验收
- [ ] 从 WeChatMsg 导出的 sqlite 能成功解析 ≥1000 条 (客户, 老板) 配对
- [ ] 配对去敏完成（手机/身份证/银行卡 0 漏）
- [ ] 配对长度过滤（老板回复 < 10 字 / > 300 字 全部丢弃）
- [ ] 配对去噪完成（"哈哈"/"嗯嗯"/单 emoji 等无信息量回复丢弃）
- [ ] 训练 jsonl 格式正确（pytest 验证）

### 2.2 训练验收
- [ ] LLaMA-Factory 配置 yaml 自动生成
- [ ] 单卡 12GB GPU 能跑通 Qwen3-8B QLoRA 训练（at least mock 配置正确）
- [ ] 训练完产出 lora.safetensors 文件
- [ ] LoRA 元数据写入 server.model_router

### 2.3 评估验收
- [ ] judge LLM (DeepSeek-R1) 接口骨架就位
- [ ] 风格相似度 ≥ 0.5（30 条盲测）
- [ ] 禁用词命中率 ≤ 1%
- [ ] 超长回复率 ≤ 1%
- [ ] 评估报告 markdown 输出

### 2.4 DPO 验收
- [ ] 从 reviews 表导出 (chosen, rejected) 配对
- [ ] 配对量 ≥ 50 触发 DPO 训练
- [ ] DPO 后 LoRA 灰度 20% 流量 24h 验证

### 2.5 工程验收
- [ ] `pytest tests/test_pipeline.py` 全绿（≥ 10 用例）
- [ ] CLI 入口：`baiyang-train --tenant tenant_0001 --data-source wechatmsg --src ./data/wxmsg.db`

---

## 3. 边界（明确不做）

- ❌ 不做基座模型预训练（直接用 Qwen3-8B-Instruct）
- ❌ 不做 RLHF / PPO（DPO 已足够）
- ❌ 不做大规模分布式训练（Phase 3 vLLM 时再说）
- ❌ 不做客户聊天图片的 VLM 分析（Phase 3）
- ❌ 不做客户人物画像的 LLM 分析（Phase 3）

---

## 4. 关键依赖

| 依赖 | 用途 | 状态 |
|---|---|---|
| WeChatMsg | 微信聊天记录解析 | 📦 待装（Windows-only） |
| PyWxDump | 备用解析 | 📦 待装 |
| LLaMA-Factory | 训练框架 | 📦 待装（GPU 机器）|
| Unsloth | 加速 + 内存优化 | 📦 待装 |
| transformers | base | 📦 待装 |
| peft | LoRA 适配器 | 📦 待装 |
| trl | DPO 训练 | 📦 待装 |
| bitsandbytes | 4-bit 量化 | 📦 待装 |
| Qwen3-8B-Instruct | base model | 📦 待下（~15GB） |
| GPU | NVIDIA 12GB+ | ⏸️ 等连大哥决定云 GPU 还是本地 |

---

## 5. 数据隐私（合规底线）

### 5.1 必做
- 老板聊天记录在客户端上加密传输（mTLS Phase 4 + 临时 AES Phase 1）
- 服务端 tenant 隔离 + AES-256 静态加密
- 365 天保留 + 用户可随时申请删除（48h 内执行）
- 训练日志脱敏（不含原文，只含 token id 统计）

### 5.2 必不做
- 不上传客户的 C 端用户聊天记录到任何第三方
- 不用客户聊天数据训练 base model（只训该客户的 LoRA）
- 不在行业飞轮（Layer 4）暴露任何客户的具体内容
- 不留任何明文备份在客户端本地（Phase 4 加密落盘）

---

## 6. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 训练数据不足（< 1000 配对）| 🔴 高 | 启用 prompt-only 兜底 + 等老板用 1 个月攒数据 |
| 训练数据老板风格不稳定 | 🟡 中 | 按时间窗口加权（最近 3 个月权重 2x） |
| LoRA 过拟合个别客户 | 🟡 中 | 客户分组训练 + dropout 调高到 0.1 |
| 训练 8 小时 OOM | 🟡 中 | gradient_checkpointing + max_seq_length 调小 |
| Qwen3-8B 中文不够强 | 🟢 低 | 备选 Qwen2.5-7B / Yi-1.5-9B |

---

## 7. 北极星追溯

- 不遗漏消息 ← Phase 1 已做
- **生成 > 手写回复** ← Phase 2 核心交付
- 促成成交 ← Phase 6 验证

**Phase 2 唯一判断标准**：连大哥 3 个朋友盲测，能不能说出 "这就是连哥的回复风格"。
