# wechat_agent · 项目专属 CLAUDE.md

> 此文件定义 wechat_agent 项目的专属规则。
> 优先级：本文件 > `~/CLAUDE.md` 的全局规则（仅项目部分被覆盖）。
> 全局工作模式（角色/语言/三铁律/阻塞规则/任务管理）继续按 `~/CLAUDE.md`。

---

## 1. 项目身份

- **项目名**：wechat_agent · 微信全自动回复 SaaS
- **目录**：`/Users/lian/wechat_agent/`
- **客户**：用微信工作的人——销售、微商、客服、接单老板
- **核心价值**：24h 全自动回复 + 像老板自己一样 + 客户用了 30 天无法离开
- **CEO**：连大哥（一人公司）
- **服务端口**：8327
- **当前阶段**：First Wave 8 件功能 + 6 件清理（2026-04-16 启动）

---

## 2. 产品定位（不可妥协）

**装在客户电脑上的 24h 微信全自动员工。**

- **技术真相**：全自动监听 + 生成 + 发送 · 不需要老板参与
- **营销外壳**：永远说"AI 副驾驶辅助" · 用户协议写"辅助工具，最终由本人决定"
- **合规兜底**：高风险消息熔断 · 紧急一键暂停 · 反封号自动调速

详见 `MISSION.md`。

---

## 3. 与其他项目严格解耦（重要）

本项目**完全独立**于以下项目（即使它们在同一 macOS 上）：

| 无关项目 | 它在 | 跟本项目的关系 |
|---|---|---|
| `whale_tracker` (~/whale_tracker/) | 加密交易 | ❌ 零关系 · 不要引用 |
| `hermes-agent` :8317 | 紫龙 | ❌ 历史 bridge 已剥离 · 走 `server/llm_client.py` |

**禁止行为**：
- ❌ 在 wechat_agent 文档/代码里出现 `白羊` `紫龙` `童虎` `HERMES 实例` `STELLA` `AutoMaAS` `8 Swarm` `Conductor` `行业飞轮` `Alignment Check`
- ❌ 在 spec 设计时引用 whale_tracker 的"师徒架构"等术语
- ❌ HTTP 调 `127.0.0.1:8317`（hermes-agent · 已剥离）
- ❌ 把 wechat_agent 的记忆写到 whale_tracker scope

**清理痕迹**：如发现旧文档/旧代码残留以上术语 · 立即修剪。

---

## 4. 关键路径速查

| 你想找 | 文件 |
|---|---|
| 产品宪法 | `MISSION.md` |
| 系统架构 | `ARCHITECTURE.md` |
| 8 周路线 | `task_plan.md` |
| 成本经济学 | `docs/cost_economics.md` |
| First Wave 三件套 | `docs/specs/first_wave/{requirements,design,tasks}.md` |
| 其他 Phase spec | `docs/specs/phase{1..7}_*/` |
| 所有路由 | `server/main.py` |
| LLM 客户端 | `server/llm_clients.py` + `server/llm_client.py` |
| Prompt 单点 | `server/prompt_builder.py`（**所有 system prompt 必须在这里 · 不准散落**）|
| 客户档案 | `server/customer_profile.py` |
| 知识库 RAG | `server/knowledge_base.py` + `server/embedder.py` |
| 反封号引擎 | `server/health_monitor.py`（B3 待建）|
| 全自动引擎 | `server/auto_send.py`（B1 待建）|
| 跟进序列 | `server/follow_up.py`（C1 待建）|
| 多账号容灾 | `server/account_failover.py`（C2 待建）|
| 训练队列 | `evolution/training_queue.py`（B2 待建 · 替换 industry_flywheel）|
| 客户端 | `client/{watcher,sender,risk_control,review_popup,version_probe}.py` |
| 数据库 schema | `db/schema.sql` + `server/models.py` |
| 测试 | `tests/test_*.py` · 全跑 `pytest -q` |
| Makefile | `make install / init-db / run / seed / test` |

---

## 5. 必看的硬约束（违反即拒绝执行）

参见 `MISSION.md` 第 4-5 节。摘要：

1. 跨 tenant 数据访问 = 红线 · 立即抛 `CrossTenantError`
2. 单条回复 ≤ 300 字（`shared/const.MAX_REPLY_LENGTH`）
3. 不生成绝对承诺词（"保证/一定/终身/稳赚/100%/包赔"）· `risk_check.contains_forbidden_word` 守门
4. 营销文案永远用"辅助/副驾驶" · 不用"全自动/无人值守"
5. prompt 必须经过 `prompt_builder.py` · 不能 inline 散落

---

## 6. 开发协作约定

- **测试**：改代码必跑 `pytest -q` · 全绿才算完成
- **新模块**：必须配套 ≥6 个单元测试
- **新表**：同时改 `db/schema.sql` + `server/models.py` + 加 alembic migration
- **新路由**：在 `server/main.py` 注册 + 写测试
- **prompt 改动**：必须改 `server/prompt_builder.py` · 不准在 generator 里硬写
- **完成标准**：只有完成和未完成 · 无"基本完成"

---

## 7. First Wave 进度（2026-04-16 启动）

| 批次 | 内容 | 状态 |
|---|---|---|
| A | C1+F2+F3+F5 + 文档清理 (MISSION/ARCHITECTURE/CLAUDE.md) | ✅ 完成 |
| B | F1 全自动引擎 + C2 训练队列 + F6 反封号 + F8 Dashboard v2 | 🚧 进行中 |
| C | F4 跟进序列 + F7 多账号容灾 + 集成总测 + C6 review_popup 默认关 | ⏳ 待开始 |
| D | 端到端 6 场景真测 + 反封号压测 + 文档同步 v4 + 启动验收 | ⏳ 待开始 |

详见 `docs/specs/first_wave/tasks.md`。
