# Phase 1 · Self-Zero Demo · Tasks

> Spec ID：`phase1_self_zero_demo`
> 任务粒度：每条 1-3 小时可完成
> 状态规则：`- [ ]` 待做 · `- [x]` 完成 · `- [s]` 跳过

---

## S0 · 项目骨架

- [x] 创建目录树 `client/ server/ pipeline/ shared/ db/ config/ tests/ docs/ scripts/ legal/`
- [ ] `pyproject.toml`（依赖 + 入口 script + ruff 配置）
- [ ] `.gitignore`（Python + venv + secrets + DB）
- [ ] `Makefile`（test/lint/run/clean 快捷方式）

## S1 · Spec 三件套

- [x] `docs/specs/phase1_self_zero_demo/requirements.md`
- [x] `docs/specs/phase1_self_zero_demo/design.md`
- [x] `docs/specs/phase1_self_zero_demo/tasks.md`（本文件）

## S2 · Shared 模块

- [ ] `shared/__init__.py`
- [ ] `shared/proto.py`（Pydantic 协议）
- [ ] `shared/const.py`（端口/路径/错误码）
- [ ] `shared/types.py`（Tenant / IntentEnum / RiskEnum）
- [ ] `shared/errors.py`（CrossTenantError / ForbiddenWordError / ...）

## S3 · Server

- [ ] `server/__init__.py`
- [ ] `server/main.py`（FastAPI app + 路由）
- [ ] `server/classifier.py`（rule mode）
- [ ] `server/generator.py`（hermes_bridge 调用）
- [ ] `server/model_router.py`（Phase 1 硬编码 hermes）
- [ ] `server/hermes_bridge.py`（HTTP + mock 模式）
- [ ] `server/tenant.py`（管理 + 隔离）
- [ ] `server/audit.py`（事件记录）
- [ ] `server/db.py`（SQLAlchemy engine + session）
- [ ] `server/models.py`（SQLAlchemy ORM 定义）
- [ ] `server/risk_check.py`（服务端 dedup + 禁用词）

## S4 · Client

- [ ] `client/__init__.py`
- [ ] `client/watcher.py`（wxautox 抽象 + mock）
- [ ] `client/sender.py`（HumanCursor 抽象 + mock）
- [ ] `client/risk_control.py`（工作时间 + 配额）
- [ ] `client/review_popup.py`（console + 预留 Qt6 接口）
- [ ] `client/version_probe.py`（微信版本探测）
- [ ] `client/encrypt.py`（DPAPI 抽象 + 占位）
- [ ] `client/api_client.py`（POST 服务端的 HTTP 客户端）

## S5 · Pipeline

- [ ] `pipeline/__init__.py`
- [ ] `pipeline/extract_chat.py`（WeChatMsg 接口占位）
- [ ] `pipeline/train_lora.py`（LLaMA-Factory 配置生成器）
- [ ] `pipeline/eval.py`（采纳率/成交率/风格匹配评估骨架）
- [ ] `pipeline/dpo_pair.py`（accept vs rewrite 配对生成）

## S6 · DB

- [ ] `db/schema.sql`（完整 schema）
- [ ] `db/migrations/0001_initial.py`（alembic 风格）
- [ ] `scripts/init_db.py`（创建 SQLite + 应用 schema）
- [ ] `scripts/seed_tenant.py`（种子数据：tenant_0001 = 连大哥）

## S7 · Config

- [ ] `config/config.example.yaml`
- [ ] `config/tenants.example.yaml`
- [ ] `.env.example`
- [ ] `config/loader.py`（合并 yaml + env）

## S8 · Tests

- [ ] `tests/__init__.py`
- [ ] `tests/conftest.py`（fixtures + db 临时）
- [ ] `tests/mocks/wxautox_mock.py`
- [ ] `tests/mocks/hermes_mock.py`
- [ ] `tests/test_proto.py`
- [ ] `tests/test_classifier.py`
- [ ] `tests/test_risk_control.py`
- [ ] `tests/test_risk_check_server.py`
- [ ] `tests/test_tenant_isolation.py`
- [ ] `tests/test_main_api.py`
- [ ] `tests/test_audit_chain.py`

## S9 · 文档

- [ ] `README.md`（项目介绍 + quickstart）
- [ ] `SETUP.md`（macOS server + Windows client 双指南）
- [ ] `RISK_CONTROL.md`（反封号策略 · 给老板看）
- [ ] `legal/user_agreement.md`（占位 · Phase 5 法务定稿）
- [ ] `legal/privacy_policy.md`（占位）
- [ ] `legal/disclaimer.md`（占位）

## S10 · 验证

- [ ] `pytest tests/ -v` 全绿
- [ ] `python -c "import server.main"` 等 8 个 import 成功
- [ ] FastAPI TestClient happy path 端到端
- [ ] grep 副作用：改动文件无破坏其他模块
- [ ] track update 记录 + status 设阻塞等连大哥验

---

## 完成定义（DoD）

- 所有 `[ ]` 变 `[x]` 或 `[s]`
- 测试 ≥15 个用例，全绿
- README 一句话能让连大哥 5 分钟启动 server
- progress.md Session 2 写完执行总结
- 等连大哥发"白羊"或"开干 Phase 2"
