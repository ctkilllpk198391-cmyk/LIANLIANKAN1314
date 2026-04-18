# Phase 1 · Self-Zero Demo · Requirements

> Spec ID：`phase1_self_zero_demo`
> 阶段：Phase 1（task_plan.md Week 1 Day 1-7）
> 验收人：连大哥
> 起草日期：2026-04-15

---

## 1. 功能范围

构建一个**端到端最小闭环**：
- 客户端（Windows · 模拟）：监听微信新消息 → 上传服务端 → 接收回复建议 → 弹审核浮窗 → 老板一键采纳 → 模拟发送
- 服务端（macOS · 实跑）：FastAPI 接收消息 → 意图分类 → 调 LLM 生成 → 返回建议 → 写审计日志
- 数据层：SQLite 兜底（Phase 2 升 PostgreSQL）+ tenant 隔离

**0 号客户**：连大哥本人（先把工具调通在自己身上验证）。

---

## 2. 验收标准（Done = 全绿）

### 2.1 功能验收
- [ ] 服务端 `uvicorn server.main:app --port 8327` 可启动并暴露 `/health` `/v1/inbound` `/v1/outbound/{msg_id}/accept` 等路由
- [ ] 客户端 watcher 在 macOS 上用 mock wxautox 能 import 不报错（真跑等 Windows）
- [ ] tenant 隔离：tenant_001 的消息不会出现在 tenant_002 的查询里
- [ ] risk_control 工作时间外（夜间）拒绝发送
- [ ] risk_control 7 天滑窗相似度 >60% 强制改写
- [ ] 审计日志每条消息有完整 chain（inbound_at / generated_at / reviewed_at / sent_at）
- [ ] hermes_bridge 通过 HTTP 调用 hermes-agent（mock 模式 + 真模式可切换）

### 2.2 测试验收
- [ ] `pytest tests/` 全绿（>15 个测试用例）
- [ ] `python -c "import server.main; import client.watcher; import shared.proto; import pipeline.extract_chat"` 全部成功
- [ ] FastAPI TestClient 能完整跑通"收消息→生成→采纳→发送"4 步流程

### 2.3 文档验收
- [ ] README.md 项目介绍 + 一句话 quickstart
- [ ] SETUP.md 完整环境配置（macOS + Windows 双指南）
- [ ] RISK_CONTROL.md 反封号策略文档
- [ ] docs/specs/phase1_self_zero_demo/{requirements,design,tasks}.md 完整

### 2.4 合规验收（永久）
- [ ] 所有 AI 生成回复 default `auto_send=False`，必须 review 后才发
- [ ] 审计日志记录 `generated_by_ai=True` 标志
- [ ] 用户协议条款占位文件 `legal/user_agreement.md` 存在

---

## 3. 边界（明确不做）

- ❌ 不做真实 wxautox 跑通（macOS 不支持，Phase 1 D7 等 Windows）
- ❌ 不做 LoRA 训练（Phase 2）
- ❌ 不做 PostgreSQL 安装（先 SQLite，Phase 2 决定升级路径）
- ❌ 不做 vLLM 多 LoRA 部署（Phase 3）
- ❌ 不做 Qt6 真实 UI（先 console review，Qt6 在 Phase 3）
- ❌ 不做支付系统（Phase 5）
- ❌ 不做 Nuitka 打包（Phase 4）
- ❌ 不克隆 HERMES 整个仓库（hermes-agent 通过 HTTP 调用，不 cp）

---

## 4. 关键依赖

| 依赖 | 用途 | 状态 |
|---|---|---|
| Python 3.11+ | 运行环境 | ✅ /opt/homebrew/bin/python3.11 |
| uv | 包管理 | ✅ /opt/homebrew/bin/uv |
| FastAPI + uvicorn | 服务端 | 📦 待装 |
| SQLAlchemy + alembic | DB ORM | 📦 待装 |
| pydantic 2.x | 数据校验 | 📦 待装 |
| pytest + httpx | 测试 | 📦 待装 |
| aiohttp | hermes_bridge HTTP | 📦 待装 |
| python-dotenv | env 加载 | 📦 待装 |
| structlog | 结构化日志 | 📦 待装 |
| (Windows) wxautox + HumanCursor | 真跑 | ⏸️ 等 Windows |

---

## 5. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| macOS 无法跑 wxautox | 🟡 中 | 用 mock wxautox 接口跑通逻辑；Windows 真跑等连大哥 |
| PostgreSQL 未装 | 🟡 中 | 先 SQLite，DB 抽象层兼容两者 |
| HERMES iLink 路线已踩坑（#107）| 🔴 高 | 不复用 hermes weixin.py，重写 wxautox 路线 |
| Phase 1 代码骨架与未来 LoRA 路由耦合 | 🟢 低 | 提前定义 model_router 接口，Phase 3 实现 |
| 一人公司单点故障 | 🟢 低 | 文档完整 + 测试覆盖，连大哥可读懂 |

---

## 6. 北极星追溯

本 Phase 对北极星贡献：
- 不遗漏消息 ← watcher 实现
- 生成 > 手写回复 ← classifier + generator 接口（实现等 LoRA）
- 促成成交 ← Phase 6 验证

**唯一判断标准** 翻译到 Phase 1：连大哥自己用，能不能 3 个朋友盲测说"这是连哥的回复"。
