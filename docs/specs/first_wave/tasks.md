# First Wave · Tasks

> 配套：`requirements.md` `design.md`
> feature_id: `first_wave`
> 执行模式：批次 A→D · 部分子任务派 Sonnet subagent 并行
> 完成标准：所有 `[x]` + 端到端 6 场景过 + pytest ≥189 全绿

---

## 批次 A · Day 0-2 · 基础设施 + 文档清理（强并行）

### A1 · C1 · `server/llm_client.py` 改名 + 兼容
- [ ] 新建 `server/llm_client.py` · 复制 `hermes_bridge.py` 内容 · 类名 → `LLMClient`
- [ ] `hermes_bridge.py` 保留 1 行：`from server.llm_client import LLMClient as HermesBridge`
- [ ] 顶部加注释说明历史 + 新代码用 `LLMClient`
- [ ] pytest 跑全 · 旧测试 0 改动通过

### A2 · F2 · 客户档案引擎
- [ ] schema：`db/schema.sql` 加 `customer_profiles` 表 + 索引
- [ ] models.py 加 `CustomerProfile` ORM
- [ ] 新建 `server/customer_profile.py` · 5 个方法（get_or_create/update_after_inbound/update_after_send/render_for_prompt/compute_vip_tier）
- [ ] `prompt_builder.py` 增加 `customer_profile_block` 参数
- [ ] `tests/test_customer_profile.py` ≥8 用例
- [ ] migration：`db/migrations/0002_customer_profile.py`

### A3 · F3 · 知识库 RAG
- [ ] schema：`db/schema.sql` 加 `knowledge_chunks` 表 + 索引
- [ ] models.py 加 `KnowledgeChunk` ORM
- [ ] 新建 `server/knowledge_base.py` · BGE embedder + numpy cosine + ingest/query/delete
- [ ] BGE embedder 包装：`server/embedder.py` · 含 mock fallback
- [ ] `prompt_builder.py` 增加 `knowledge_block` 参数
- [ ] 新建 `scripts/ingest_knowledge.py` · CLI 用 · 上传 markdown/csv
- [ ] `tests/test_knowledge_base.py` ≥10 用例（含 mock embedder）
- [ ] `tests/test_embedder.py` ≥3 用例
- [ ] 在 `pyproject.toml` 加依赖：`sentence-transformers` `numpy`

### A4 · F5 · 意图升级
- [ ] `shared/types.py` 加 `EmotionEnum`
- [ ] `shared/proto.py` `IntentResult` 加 `emotion` 字段
- [ ] `server/classifier.py` 升级：`mode='hybrid'` + `_classify_llm` 实装 + `_guess_emotion_rule`
- [ ] `prompt_builder.py` 增加 `emotion_block` 段
- [ ] `tests/test_classifier_hybrid.py` ≥12 用例（情绪边界）
- [ ] 现有 `test_classifier.py` 回归 0 破坏

### A5 · C3 · MISSION.md v2（subagent · sonnet）
- [ ] 派 Sonnet subagent 重写 MISSION.md（按 design §10 C3 规范）
- [ ] 删白羊/紫龙/童虎/HERMES/STELLA/AutoMaAS/8 Swarm
- [ ] 加全自动 + 副驾驶外壳明文宪法
- [ ] 我（Opus）审一遍

### A6 · C4 · ARCHITECTURE.md v2（subagent · sonnet）
- [ ] 派 Sonnet subagent 按 design §10 C4 规范重写
- [ ] 数据流图按全自动直发流程重画
- [ ] 8 模块拓扑 + 新表清单
- [ ] 我（Opus）审一遍

### A7 · C5 · wechat_agent/CLAUDE.md
- [ ] 新建 `wechat_agent/CLAUDE.md`
- [ ] 项目背景 + 核心定位 + 关键路径 + 与 ~/CLAUDE.md 解耦说明

---

## 批次 B · Day 2-5 · 核心引擎落地

### B1 · F1 · 真全自动引擎
- [ ] tenants.config_json 加 `auto_send_enabled` `high_risk_block` `quota_per_day` `pause_until` `boss_phone_webhook`
- [ ] 新建 `server/auto_send.py` · `AutoSendDecider` 类 · 5 种 decision
- [ ] `server/main.py` /v1/inbound 末尾接入 `decide` + `trigger_send`
- [ ] 新增路由：`POST /v1/control/{tenant}/pause` `POST /v1/control/{tenant}/resume` `GET /v1/control/{tenant}/status`
- [ ] WebSocket 推送增加 `auto_send_command` event 类型
- [ ] 飞书通知 mock：`server/notifier.py` · 接 webhook（先 mock）
- [ ] `tests/test_auto_send.py` ≥10 用例
- [ ] `tests/test_control_api.py` ≥4 用例

### B2 · C2 · training_queue
- [ ] schema：`db/schema.sql` 加 `training_queue` 表
- [ ] models.py 加 `TrainingQueue` ORM
- [ ] 新建 `evolution/training_queue.py` · append/export/stats
- [ ] 在 main.py /v1/outbound/{msg_id}/decide 末尾追加 `training_queue.append`
- [ ] 删除 `evolution/industry_flywheel.py`
- [ ] 删除 `tests/test_industry_flywheel.py` → 改名 `tests/test_training_queue.py` ≥6 用例
- [ ] `evolution/__init__.py` 更新

### B3 · F6 · 反封号引擎
- [ ] schema：`account_health_metrics` + `account_health_status` 表
- [ ] models.py 加 `AccountHealthMetric` `AccountHealthStatus` ORM
- [ ] 新建 `server/health_monitor.py` · 5 维度 + 评分公式 + tick_all
- [ ] APScheduler 集成：在 `server/main.py` lifespan 启动定时任务
- [ ] 新建 `server/scheduler.py` · 集中管理 cron jobs
- [ ] 新增路由：`GET /v1/health/{tenant}` `POST /v1/health/{tenant}/recover`
- [ ] `tests/test_health_monitor.py` ≥10 用例（5 维度边界 + 评分 + 三档响应）
- [ ] 在 `pyproject.toml` 加依赖：`apscheduler`

### B4 · F8 · Dashboard 升级（subagent · sonnet）
- [ ] 新接口 5 个：/dashboard/{tenant}/v2 /trend /customers /funnel /benchmark
- [ ] `server/dashboard.py` 升级 · 加 5 个 builder 方法
- [ ] 客户分级算法（A/B/C）· VIP 自动打标
- [ ] 成交漏斗算法（intent 流转）
- [ ] 同行对标静态基线（先 mock · Phase 7 替）
- [ ] 新模板 `server/templates/dashboard.html` 用 chart.js（CDN）
- [ ] `server/weekly_report.py` · 渲染 markdown · 飞书 webhook（mock）
- [ ] `tests/test_dashboard_v2.py` ≥8 用例

---

## 批次 C · Day 5-9 · 跟进 + 容灾 + 集成

### C1 · F4 · 跟进序列引擎
- [ ] schema：`follow_up_tasks` 表 + 索引
- [ ] models.py 加 `FollowUpTask` ORM
- [ ] 新建 `server/follow_up.py` · `FollowUpEngine` + 4 种 task_type + `FollowUpTemplates`
- [ ] APScheduler 注册：每 1 分钟 tick
- [ ] main.py /v1/inbound 末尾：order intent → `follow_up.schedule`
- [ ] 新增路由：`GET /v1/follow_up/{tenant}` `DELETE /v1/follow_up/{task_id}`
- [ ] 跟进文案生成：复用 generator + 专属 system prompt
- [ ] `tests/test_follow_up.py` ≥8 用例

### C2 · F7 · 多账号容灾
- [ ] tenants.config_json schema 加 `accounts` `active_account_id` 字段
- [ ] schema：`account_failover_log` 表
- [ ] models.py 加 `AccountFailoverLog` ORM
- [ ] 新建 `server/account_failover.py` · `AccountFailover` 类
- [ ] health_monitor 红灯回调 → `auto_failover`
- [ ] AutoSendDecider 用 `failover.get_active` 决定推到哪个 client
- [ ] 新增路由：`GET /v1/accounts/{tenant}` `POST /v1/accounts/{tenant}/switch/{account_id}`
- [ ] `tests/test_account_failover.py` ≥6 用例

### C3 · 集成总测
- [ ] 全 prompt_builder 调用方更新（generator/follow_up）传 customer_profile + knowledge + emotion
- [ ] generator.generate 集成 RAG 召回
- [ ] 修复任何回归 · 跑全 pytest 全绿
- [ ] 修 conftest fixture · 新表自动 import 注册到 Base.metadata

### C4 · C6 · review_popup 默认关
- [ ] `client/review_popup.py` 加 `mode='auto'` 选项 · 默认不弹
- [ ] 仅在 `auto_send_enabled=False` 或 server 推送 `risk=high` 时弹
- [ ] `tests/test_review_popup.py`（如无则新建）+2 用例

---

## 批次 D · Day 9-11.5 · 端到端真路径测试

### D1 · 6 场景脚本
- [ ] 新建 `tests/e2e/test_first_wave_e2e.py`
- [ ] 场景 1：陌生新客首次询价
- [ ] 场景 2：老客复购（先注入 customer_profile 历史）
- [ ] 场景 3：客户砍价 + 临门一脚
- [ ] 场景 4：客户投诉 + 高风险熔断
- [ ] 场景 5：客户下单 + 30 分钟自动催付款
- [ ] 场景 6：长尾询价 + RAG 召回产品参数
- [ ] 每场景断言：DB 状态 + audit 链 + WS 推送 + final reply 内容

### D2 · 反封号压测
- [ ] 新建 `tests/stress/test_health_stress.py`
- [ ] 1000 条消息高相似度 30% · 验证降速
- [ ] IP 切换 5 次 · 验证红灯 + failover
- [ ] follow_up 1000 task 同时到点 · 验证不卡死

### D3 · 文档同步
- [ ] 更新 `STATUS_HANDOFF.md` 到 v4（First Wave 完成）
- [ ] 更新 `progress.md` 加 Session 3
- [ ] 更新 `task_plan.md` 标 First Wave 完成
- [ ] 更新 `findings.md` 加 RAG/embedder/health 模型选型说明
- [ ] 更新 `README.md` 反映新功能

### D4 · 启动验收
- [ ] `make init-db` 干净跑过（含新表）
- [ ] `make run` server 起来 · 所有路由在 OpenAPI
- [ ] curl 每个新路由都 200
- [ ] pytest ≥189 全绿
- [ ] grep TODO/FIXME → 0
- [ ] aivectormemory 记忆 3 条（First Wave 完成里程碑 + RAG 选型 + 反封号公式）

---

## 风险 & 回退

| 风险 | 缓解 |
|---|---|
| BGE 模型 100MB 下载失败 | mock embedder fallback · 不阻塞测试 |
| APScheduler 与 uvicorn lifespan 冲突 | 用 BackgroundScheduler + 显式 start/shutdown |
| 旧 hermes_bridge 测试因别名失败 | C1 保留 alias 行 · 全跑通后再考虑彻底删 |
| LLM API 4xx/5xx 影响真路径测试 | 测试用 mock=true · 真接通走单独 smoke test |
| customer_profile 大量并发更新 race | UPSERT 加 UNIQUE(tenant_id, chat_id) |

---

## 完成验收（连大哥拍）

- [ ] 8 件功能全 [x]
- [ ] 6 件清理全 [x]
- [ ] 端到端 6 场景全过
- [ ] pytest ≥189 全绿
- [ ] 文档同步 v4
- [ ] 阻塞清空 · 等连大哥发"验收"
