# Phase 3 · vLLM 多 LoRA 部署 · Requirements

> Spec ID：`phase3_vllm_multi_lora`
> 阶段：Phase 3（task_plan.md Week 3 Day 15-21）
> 起草日期：2026-04-15

---

## 1. 功能范围

把多客户的专属 LoRA 全部部署到 vLLM 实例，实现 <1ms 热切换 + 共享 base model 内存优化。

### 1.1 子模块
1. **vLLM 启动**：Qwen3-8B base + N 个 LoRA adapter
2. **LoRA 注册中心**：tenant_id → lora_path 映射
3. **HermesBridge 升级**：route lora:tenant_xxx → vLLM
4. **健康监控**：vLLM 进程 watchdog + GPU 利用率
5. **灰度发布**：新 LoRA 上线 → 20% 流量验证 → 全量
6. **审核浮窗 Qt6**：从 Phase 1 console 升级到桌面 UI

---

## 2. 验收标准

### 2.1 部署
- [ ] vLLM 0.6+ 启动 Qwen3-8B + 5 个 LoRA（mock 数据）
- [ ] LoRA 热切换 < 5ms（实测）
- [ ] 单卡 A100 80G 同时挂 100+ LoRA 不 OOM
- [ ] LoRA 注册中心从 `models/{tenant}/lora/` 自动扫描

### 2.2 路由
- [ ] hermes_bridge 接收 `model_route=lora:tenant_xxx` → 转 vLLM
- [ ] tenant_xxx 的 LoRA 不存在 → fallback 到 hermes_default
- [ ] 高风险 intent → 强制 claude_sonnet（绕过 LoRA）

### 2.3 灰度
- [ ] 新 LoRA 部署后 24h 灰度 20%
- [ ] 采纳率不降 → 全量
- [ ] 采纳率降 > 5% → 自动回滚 + 告警

### 2.4 客户端
- [ ] Qt6 浮窗 review_popup（替代 Phase 1 console）
- [ ] 一键采纳 / 编辑 / 拒绝 / 真人接管 4 按钮
- [ ] 系统托盘 + 通知音

### 2.5 工程
- [ ] `pytest tests/test_vllm_router.py` 全绿
- [ ] CLI: `baiyang-deploy-lora --tenant tenant_0001 --lora-path ./models/tenant_0001/lora`

---

## 3. 边界

- ❌ 不做模型预训练
- ❌ 不做分布式推理（单卡足够，多卡 Year 2）
- ❌ 不做 vLLM 源码修改（用官方 0.6+ 现成功能）
- ❌ 不做 Web Dashboard（Phase 5）

---

## 4. 关键依赖

| 依赖 | 版本 | 说明 |
|---|---|---|
| vLLM | ≥ 0.6 | 多 LoRA 必需 |
| Qwen3-8B-Instruct | safetensors | base ~16GB |
| PyQt6 | ≥ 6.7 | Qt6 浮窗 |
| GPU | A100 80G × 1 | 起步 |

---

## 5. KPI

| 指标 | 目标 |
|---|---|
| LoRA 热切换 | < 5ms |
| 单卡 LoRA 上限 | ≥ 100 |
| 灰度自动回滚 | < 5min |
| Qt6 浮窗响应 | < 100ms |
