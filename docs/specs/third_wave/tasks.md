# Third Wave (TDW) · Tasks

> feature_id: `third_wave`
> 完成标准：所有 [x] + e2e 6 场景过 + pytest ≥412 全绿

---

## 批次 A · Day 0-3 · 4 件强并行

### A1 · T1 内容摄入引擎（我做）
- [ ] schema + models.py 加 content_uploads 表 + ORM
- [ ] server/content_ingest.py 多格式解析 + 自动分类
- [ ] client/content_watcher.py watchdog 监听 + 上传
- [ ] main.py 加路由 POST /content/upload + GET /list + DELETE
- [ ] pyproject.toml 加 watchdog + python-docx 依赖
- [ ] tests/test_content_ingest.py ≥10

### A2 · T3 行动 Dashboard（subagent · sonnet）
- [ ] server/customer_pipeline.py 待成交 + urgency 排序
- [ ] server/action_recommender.py 5 类 action 规则引擎
- [ ] dashboard.py 加 build_v3() 整合 v2 + pipeline + actions + multi_account
- [ ] templates/dashboard.html v3 加待成交卡片 + 行动清单
- [ ] 路由 GET /v1/dashboard/{tenant}/v3
- [ ] tests/test_customer_pipeline.py + test_action_recommender.py ≥12

### A3 · T4 数据护城河（subagent · sonnet）
- [ ] server/encryption.py TenantKMS + fernet backend
- [ ] LoRA 加密集成（pipeline/train_lora.py 落盘前）
- [ ] customer_profile 敏感字段加密（_encrypted 字段）
- [ ] 加密 key dir gitignore
- [ ] tests/test_encryption.py ≥8
- [ ] pyproject.toml 加 cryptography 依赖

### A4 · T5 数据所有权（subagent · sonnet）
- [ ] legal/data_ownership.md 协议草拟
- [ ] server/data_export.py export_chats CSV/JSON
- [ ] server/data_deletion.py request + cancel + execute_overdue
- [ ] client/consent_page.py 首装授权页
- [ ] 路由 POST /v1/account/{tenant}/export · /delete_request · /delete_cancel
- [ ] tests/test_data_export.py + test_data_deletion.py ≥8

---

## 批次 B · Day 3-5 · T2 + 集成

### B1 · T2 营销方案生成器（我做 · 依赖 T1）
- [ ] schema + models.py 加 marketing_plans 表 + ORM
- [ ] server/marketing_plan.py MarketingPlanGenerator
- [ ] T1 content_ingest 触发：source_tag in [产品,活动] → 自动 generate
- [ ] activate 路径：朋友圈 → moments_posts · 群发 → follow_up_tasks
- [ ] 路由 POST /marketing/generate · GET /list · POST /activate
- [ ] tests/test_marketing_plan.py ≥8

### B2 · main.py 全集成
- [ ] App 加 content_ingest / marketing_plan / pipeline_builder / action_recommender / kms / exporter / deletion_mgr
- [ ] _init_components 初始化所有
- [ ] _start_scheduler 加 deletion_mgr.execute_overdue 每天 03:00
- [ ] 跑全 pytest 全绿（≥412）

---

## 批次 C · Day 5-7.5 · e2e + 文档 + 验收

### C1 · 端到端 6 场景
- [ ] tests/e2e/test_third_wave_e2e.py
- [ ] 场景 1：上传 .md → KB 召回
- [ ] 场景 2：上传 .csv → 询价 RAG 用
- [ ] 场景 3：上传"新品.md" → marketing_plan 自动生成 → activate → moments 入队
- [ ] 场景 4：dashboard /v3 含 pipeline + actions
- [ ] 场景 5：导出 csv（仅原始聊天 · 不含训练资产）
- [ ] 场景 6：删除请求 → 30 天 grace 状态可见

### C2 · 文档同步 v6（subagent · sonnet）
- [ ] STATUS_HANDOFF v6（TDW 完成 · 模块清单 · 测试数）
- [ ] progress 加 Session 5
- [ ] task_plan 标 TDW 完成
- [ ] findings 加 § 13 数据护城河 + 客户锁定经济学
- [ ] README 加 TDW 5 件能力

### C3 · 启动验收
- [ ] uvicorn 启动 + curl 新路由
- [ ] grep TODO/FIXME = 0
- [ ] aivectormemory 记忆 3 条（TDW 完成 / KMS 设计 / pipeline 算法）

---

## 不做
- ❌ 真接 AWS KMS（Phase 4）
- ❌ Web Dashboard 改前端框架（继续 chart.js）
- ❌ 真删 LoRA 文件（30 天 grace 后才允许）
