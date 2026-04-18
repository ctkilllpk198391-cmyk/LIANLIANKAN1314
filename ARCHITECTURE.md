# wechat_agent · 系统架构 v2

> 技术文档 · 给维护者看
> 不是 marketing 文档（`marketing/landing/index.html`）
> 不是产品手册（`RISK_CONTROL.md`）

---

## 1. 全景图

```
┌─ 客户端（Windows · wxauto） ─────────────────────────────┐
│                                                           │
│  wxauto on_message → client.watcher                      │
│    → HTTPS POST /v1/inbound                               │
│                                                           │
│  client.sender（HumanCursor + wxauto.SendMsg）           │
│    ← WS 推送（auto_send 决策后直接触发）                  │
│                                                           │
│  高风险 / 手动模式：review_popup（默认关 · 可选弹）       │
└───────────────────────────────────────────────────────────┘
                     │ HTTPS / WSS
                     ▼
┌─ 服务端（macOS dev / Linux prod · :8327） ───────────────┐
│                                                           │
│  FastAPI server.main                                      │
│    POST /v1/inbound                                       │
│    POST /v1/outbound/{msg_id}/sent                        │
│    POST /v1/control/{tenant}/pause|resume                 │
│    GET  /v1/customers/{tenant}/{chat_id}  PATCH           │
│    POST /v1/knowledge/{tenant}/ingest|query               │
│    GET  /v1/follow_up/{tenant}  DELETE /v1/follow_up/{id} │
│    GET  /v1/health/{tenant}  POST /v1/health/{tenant}/recover │
│    GET  /v1/accounts/{tenant}  POST /v1/accounts/{tenant}/switch/{id} │
│    GET  /v1/dashboard/{tenant}/v2|trend|customers|funnel  │
│    WS   /v1/ws/{tenant_id}                                │
│    GET  /v1/health                                        │
│                                                           │
│  LLM 直连（server/llm_clients.py）:                       │
│    DeepSeek V3.2  → 90% 场景 · ¥0.0013/条               │
│    GLM-5.1        → 高风险 10% · ¥0.0057/条             │
│    豆包 1.5 Pro   → 拟人化 · 备选                        │
│    MiniMax M2.7   → Token Plan 备选                      │
│    Claude Sonnet  → 国际客户备份                          │
│    LocalVLLM      → Phase 7+ LoRA                        │
│                                                           │
│  APScheduler 后台 jobs:                                   │
│    每 1 min:  follow_up.tick                              │
│    每 5 min:  health_monitor.score_all                    │
│    每天 02:00: customer_profile.weekly_compact            │
│    每周一 09:00: dashboard.weekly_report → 飞书           │
└───────────────────────────────────────────────────────────┘
```

---

## 2. 数据流（全自动直发 · v2）

```
┌─ 客户微信发消息 ──────────────────────────────┐
│ wxauto on_message → client.watcher            │
│ → POST /v1/inbound                            │
└──────────────────┬────────────────────────────┘
                   ▼
┌─ /v1/inbound pipeline ───────────────────────┐
│ 1. tenant.enforce_isolation                   │
│ 2. classifier.classify (rule + emotion)       │
│ 3. customer_profile.get_or_create(chat_id)    │
│ 4. knowledge_base.query(text, top_k=3)        │
│ 5. prompt_builder.build (profile + RAG)       │
│ 6. generator.generate                         │
│ 7. risk_check (forbidden + dedup · 重写 ≤3)  │
│ 8. audit.log("suggestion_generated")          │
└──────────────────┬────────────────────────────┘
                   ▼
┌─ AutoSendDecider ────────────────────────────┐
│ risk==HIGH or quota_exceeded:                 │
│   → audit "auto_send_blocked"                 │
│   → notify_boss（飞书 webhook · mock 可选）   │
│   → 不发                                      │
│ auto_send_enabled and healthy:                │
│   → push WS → client.sender → wxauto.SendMsg │
│   → POST /v1/outbound/{msg_id}/sent           │
│ else:                                         │
│   → review queue（老板手动确认）              │
└──────────────────┬────────────────────────────┘
                   ▼
┌─ 后处理（async） ─────────────────────────────┐
│ customer_profile.update_after_reply           │
│ health_monitor.record_send                    │
│ follow_up.maybe_schedule (intent==ORDER)      │
│ training_queue.append (accepted/edited)       │
└───────────────────────────────────────────────┘
```

5 个 audit 节点：`inbound_received` → `suggestion_generated` → `auto_send` / `blocked` → `sent` → 完成

---

## 3. First Wave 模块拓扑（8 新模块）

```
                ┌── F2 customer_profile ──┐
                │                         │
C1 llm_clients ─┤── F3 knowledge_base ────┼─→ F1 AutoSendDecider ─┐
                │   (+ BGE embedder)      │                        │
                │── F5 classifier ────────┘                        │
                │   (rule + emotion)                               ├─→ F4 follow_up
                │                                                  │
                ├── F6 health_monitor ─── 红灯触发 ───────────────┤
                │   (5 维度 + scheduler)                           │
                └── F7 account_failover ── active_account ────────┘
                                                                   │
C2 training_queue ─────────────────── 接 F1 后处理 ──────────────┘

F8 dashboard v2 ── 聚合上述所有模块数据 ── GET /v1/dashboard/...
```

### 模块职责速查

| 模块 | 文件 | 核心职责 |
|---|---|---|
| F1 | `server/auto_send.py` | AutoSendDecider · 三分支决策 · 飞书通知 |
| F2 | `server/customer_profile.py` | 档案读写 · VIP 分级 · prompt 渲染 |
| F3 | `server/knowledge_base.py` | chunk 摄入 · BGE 向量 · cosine 召回 |
| F4 | `server/follow_up.py` | 4 类定时跟进 · APScheduler tick |
| F5 | `server/classifier.py` | hybrid rule/LLM · 情绪四分类 |
| F6 | `server/health_monitor.py` | 5 维评分 · 三档自动响应 |
| F7 | `server/account_failover.py` | 多账号切换 · 红灯自动容灾 |
| F8 | `server/weekly_report.py` + dashboard API | 趋势 / 漏斗 / 对标 / 周报 |
| C1 | `server/llm_clients.py` | 多模型直连 · LLMRegistry |
| C2 | `evolution/training_queue.py` | review 决策写队列 · LoRA 数据导出 |

---

## 4. 数据库

### 现有表（保留）
- `tenants` · `messages` · `suggestions` · `reviews`
- `sent_messages` · `audit_log` · `subscriptions`

### First Wave 新增表

| 表名 | 用途 |
|---|---|
| `customer_profiles` | 客户档案 · nickname / vip_tier / 购买记录 / 情绪标签 |
| `knowledge_chunks` | RAG 分块 · embedding JSON · source / tags |
| `follow_up_tasks` | 定时跟进 · task_type / scheduled_at / status |
| `account_health_metrics` | 5 维原始指标时序 |
| `account_health_status` | 最新评分 / level / paused_until |
| `account_failover_log` | 切号记录 · from/to/reason/auto |
| `training_queue` | review 决策队列 · weight / emotion / intent |

`tenants.config_json` 新增字段：`auto_send_enabled` / `high_risk_block` / `quota_per_day` / `boss_phone_webhook` / `accounts[]` / `active_account_id`

Phase 1 SQLite · Phase 2 升 PostgreSQL + pgvector（embedding 列改 vector(384)）

---

## 5. 安全模型

### 5.1 多租户隔离
- `tenant.TenantManager.enforce_isolation()` 强制 · 跨 tenant → `CrossTenantError` + audit
- 数据：行级隔离 + AES-256 静态加密

### 5.2 凭证管理
- API key 走 `.env`（不进 git）
- 客户端 token Windows DPAPI 保护
- 生产 docker secret

### 5.3 审计日志
- 365 天保留 · append-only · 结构化 JSON
- 关键节点：inbound / suggestion / auto_send / blocked / sent / failover

---

## 6. 部署

### 6.1 dev (macOS)
```bash
make install && make init-db && make seed && make run
```

### 6.2 prod (Linux + Docker)
```bash
docker compose up -d
docker compose logs -f wechat-agent-server
```

### 6.3 监控
```bash
cd monitoring && docker compose up -d
# Grafana http://localhost:3000 (admin / changeme)
# Prometheus :9090  AlertManager :9093
```

### 6.4 客户端 Windows
```powershell
.\scripts\install_windows.ps1 -ServerUrl https://api.example -TenantId tenant_0001
```

---

## 7. 关键决策与权衡

| 决策 | 选择 | 理由 |
|---|---|---|
| LLM 调用 | 直连多厂商 API | hermes_bridge 已重构为 llm_clients · 无外部 agent 依赖 |
| 默认路由 | DeepSeek V3.2 | ¥0.0013/条 · 性价比第一 |
| 高风险路由 | GLM-5.1 | 中文 BenchLM 84 · 共情能力强 |
| embedding | BAAI/bge-small-zh-v1.5 | 384 维 · ~100MB · macOS M4 50ms/chunk |
| 向量存储 | numpy cosine (Phase 1) | <1000 chunk 性能足够 · Phase 2 升 pgvector |
| 数据库 | SQLite → PostgreSQL | Phase 1 零配置 · Phase 2 切 PG |
| 微信对接 | UI Automation | iLink 不通 (#107) · 合规风险最低 |
| 全自动策略 | 直发 + 高风险熔断 | 副驾驶外壳 + 合规兜底 |
| client 打包 | Nuitka | 反编译难 + 性能好 |
| WebSocket | WS 长连接 | 实时性高 · 减少 server 负载 |

---

## 8. 进展状态（2026-04-16）

| 阶段 | 状态 |
|---|---|
| Phase 0 立项 | 完成 |
| Phase 1 Self-Zero Demo | macOS 部分完成（73 测试全绿） |
| Phase 1.5 打磨 | 完成 |
| **First Wave（F1-F8 + C1-C6）** | **in_progress · 目标 11.5 工作日** |
| Phase 2 LoRA 管线 | 骨架完成 · 等 GPU |
| Phase 3 vLLM 多 LoRA | spec 完成 · 等 GPU + 客户量 |
| Phase 4 客户端打包 | spec 完成 · 等 Windows + 证书 |
| Phase 5 商业化 | billing/dashboard 骨架完成 · 等微信支付 |
| Phase 6 PMF | landing 完成 · 等销售 |
| Phase 7 放大 | 等 ≥10 客户 |
