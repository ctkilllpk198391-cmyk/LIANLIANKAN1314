# Third Wave (TDW) · 5 件落地闭环 · Requirements

> 立项：2026-04-16 · 周期：7.5 工作日（macOS 全跑通）
> 目标：客户拿到的是"魔法文件夹 + 行动 Dashboard + 数据锁死"完整闭环
> 商业意义：让客户用 30 天后**沉没成本无法迁移** · 续费率 90%+

---

## 一、产品力北极星

> **老板每天用 → 越用越离不开 → 离开等于失去自己。**

---

## 二、5 件功能 · 验收标准

### T1 · 内容摄入引擎（魔法文件夹）
**目标**：老板把想法/新项目/资料丢进文件夹 → AI 自动消化 → 立即影响私聊回复 + 触发营销方案。
**验收**：
- [x] `client/content_watcher.py` · watchdog 监听 `~/wechat_agent_input/` · 检测新文件 → 上传
- [x] `server/content_ingest.py` · 多格式解析路由：
  - md/txt/docx → 切 chunk → embedder → KB
  - csv → 价格/库存表 → KB
  - jpg/png → vlm 描述 → KB
  - mp3/mp4/m4a → asr 转写 → KB
- [x] 自动分类 tag（产品/活动/反馈/培训/价格）
- [x] 上传后立即触发：(1) RAG 立即可召回 (2) marketing_plan 自动生成（T2）(3) 进训练队列
- [x] 新表 `content_uploads`（file_name/file_type/size/parsed_chunks/source_tag/uploaded_at）
- [x] API：`POST /v1/content/{tenant}/upload` · `GET /v1/content/{tenant}` · `DELETE /v1/content/{file_id}`
- [x] tests/test_content_ingest.py ≥10 用例

### T2 · 营销方案生成器（朋友圈+私聊+群发）
**目标**：基于上传的新资料 → 自动生成 1 套完整营销方案 · 老板审核 → 一键启用。
**验收**：
- [x] `server/marketing_plan.py` · 输入"新产品资料/活动" → 输出 MarketingPlan：
  - 朋友圈 5 条（不同时间点 · 不同角度）
  - 私聊 SOP（5+ 触发-话术对）
  - 群发文案（按客户分级 A/B/C 各一条）
  - 预估效果（订单数 + 营收）
- [x] 生成 LLM 用 Doubao 拟人冠军 · prompt 含老板风格 + 行业模板 + 心理学触发器
- [x] 新表 `marketing_plans`（plan_id/source_content_id/payload_json/status/created_at）
- [x] API：`POST /v1/marketing/{tenant}/generate?source=xxx` · `GET /v1/marketing/{tenant}` · `POST /v1/marketing/{plan_id}/activate`
- [x] activate → 朋友圈进 moments_posts · 私聊 SOP 进 customer_profile fact · 群发进 follow_up_tasks
- [x] tests/test_marketing_plan.py ≥8 用例

### T3 · 行动型 Dashboard（多账号视图 + 待成交 + 推荐行动）
**目标**：老板每天打开 dashboard 看"今天该跟谁、说什么"。
**验收**：
- [x] `server/customer_pipeline.py` · 算"待成交"客户列表（VIP+stage=NEAR/COMPARE）
- [x] `server/action_recommender.py` · 每客户算下一步推荐：
  - 沉睡 30 天 → "建议主动关怀"
  - 询价后 24h 无回 → "建议催一下"
  - 投诉未解决 → "建议人工接管"
  - 复购窗口 → "建议推老配方"
- [x] dashboard 升级：
  - 多微信号视图（accounts × health_score × 客户数 × 今日成交）
  - 今日待成交（top 10 · 紧迫度排序 · 一键采纳/编辑/跳过）
  - 今日 AI 已自动处理摘要
  - 营销方案待审区
- [x] 新接口：`GET /v1/dashboard/{tenant}/v3`（汇总 v2 + pipeline + actions）
- [x] HTML 模板加"今日行动清单"卡片（chart.js 已在）
- [x] tests/test_customer_pipeline.py + test_action_recommender.py ≥12 用例

### T4 · 数据护城河（加密 + KMS 抽象 · 客户锁定核心）
**目标**：客户走了拿不到训练资产 · 等于失去 3 个月积累的"分身"。
**验收**：
- [x] `server/encryption.py` · per-tenant AES-256 + KMS 抽象层
  - 本地 dev：用 cryptography fernet · key 存 `~/.wechat_agent_keys/`（gitignore）
  - prod：留接口给 AWS KMS / 阿里云 KMS（Phase 4 接）
- [x] LoRA 文件加密存储（`pipeline/train_lora.py` 落盘前 encrypt）
- [x] 训练队列 / 客户档案 / 营销方案：DB 字段 AES-256 加密（敏感字段 only · 不全表）
- [x] 解密 key 永不下发客户端（API 返回纯明文）
- [x] tests/test_encryption.py ≥8 用例

### T5 · 客户授权 + 数据所有权（合规 + 离开流程）
**目标**：协议明文 + 合规导出（仅原始聊天） + 不导训练资产。
**验收**：
- [x] `legal/data_ownership.md` 数据条款（明文写：原始数据可导出 · 训练资产归 wechat_agent）
- [x] `server/data_export.py` · `export_chats(tenant_id, format="csv|json")` 仅原始消息+回复（合规）
- [x] `server/data_deletion.py` · `request_deletion(tenant_id)` 异步删除（30 天 grace · GDPR）
- [x] API：`POST /v1/account/{tenant}/export?format=csv` · `POST /v1/account/{tenant}/delete_request`
- [x] 客户首次安装时弹"数据使用授权"页（client/consent_page.py）
- [x] 用户协议 v3 加数据章节
- [x] tests/test_data_export.py + test_data_deletion.py ≥6 用例

---

## 三、不做的事
- ❌ 真接 AWS KMS（Phase 4 部署时再接 · 现在用本地 fernet 抽象）
- ❌ 真删 LoRA 文件（30 天 grace 后才能删 · 离当前太远）
- ❌ Web Dashboard 改前端框架（继续用 chart.js + HTML · 不引 Vue/React）

---

## 四、验收准则
1. pytest 367 + TDW ≥45 用例 → ≥412 全绿
2. 端到端 6 场景（魔法文件夹 → 营销方案 → 待成交 → 数据导出）
3. 0 个 TODO/FIXME · 0 个 mock 散落
4. MISSION/ARCHITECTURE/STATUS_HANDOFF 同步到 v6
5. 客户使用手册更新（添加魔法文件夹 + 行动 Dashboard 操作指南）

---

## 五、外部依赖
| 资源 | 谁提供 | 卡哪个功能 |
|---|---|---|
| 法务条款审核 | 连大哥（律师 ¥2-3K）| T5 数据章节定稿 |
| Windows + watchdog | 连大哥 | T1 真测 |
| AWS/阿里云 KMS | Phase 4 | T4 prod 加密 |
