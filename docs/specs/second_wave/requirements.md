# Second Wave (SDW) · 8 件拟人化护城河 · Requirements

> 立项：2026-04-16 · 周期：11 工作日（macOS 全跑通）
> 目标：把"像真人度"从 First Wave 的 85% 推到 95%+ · 心理学触发让成交率 +25%
> 依据：本仓库 First Wave 完成 + 上一会话用户调研结论

---

## 一、产品力北极星

> **不让客户分清是 AI 还是人 · 让客户立即想下单。**

---

## 二、8 件功能 · 验收标准

### S1 · 节奏拟人引擎（最关键 · 微商工具都没做）
**目标**：消息从"机器人 0.5 秒回"变"真人 1-3 秒打字 + 长句分段"。
**验收**：
- [x] `server/typing_pacer.py` · 按消息长度高斯分布算延迟（μ=1.5s · σ=0.5s · 长句 +0.05s/字）
- [x] `server/message_splitter.py` · 长 reply 拆 2-3 段 · 每段间隔 0.8-1.5s
- [x] 夜间模式：00:00-07:00 客户消息 → 回 "刚醒看到~ 早上联系您可以吗？" · 不熬夜回
- [x] WS push 加 `delay_ms` 字段 · client 收到后等 delay_ms 才发
- [x] tenant config 加 `pacing_enabled` `nighttime_off`
- [x] tests/test_typing_pacer.py + test_message_splitter.py ≥10 用例

### S2 · 心理学触发器引擎（成交率 +25% 关键）
**目标**：4 维度（intent/emotion/客户档案/对话阶段）自动选 Cialdini 触发器。
**验收**：
- [x] `server/psych_triggers.py` · 6 类触发器：scarcity/social_proof/reciprocity/loss_aversion/authority/commitment
- [x] 自动选触发器决策表（intent×emotion×stage → trigger_type）
- [x] prompt_builder 集成 `psych_block` 段（被 generator 用）
- [x] 客户对话阶段识别：探索 → 询价 → 砍价 → 临门 → 成交 → 售后
- [x] tests/test_psych_triggers.py ≥12 用例

### S3 · 6 行业模板池（自动检测 + 风格微调）
**目标**：6 个垂直行业 prompt 模板 · 客户安装时选 · AI 自动微调风格。
**验收**：
- [x] `server/industry_templates/{微商,房产,医美,教培,电商,保险}.md`（6 个 markdown）
- [x] `server/industry_router.py` · industry_id → 行业 prompt 段
- [x] tenant config 加 `industry` 字段
- [x] AI 自动检测：客户上传聊天 3 个月 → 调 LLM 推荐行业 + 风格
- [x] prompt_builder 集成 `industry_block` 段
- [x] tests/test_industry_router.py ≥6 用例

### S4 · 多模态：图片理解（Qwen3-VL）
**目标**：客户发"这个怎么卖"+ 图片 · AI 看图回价。
**验收**：
- [x] `server/vlm_client.py` · Qwen3-VL API 包装（mock fallback）
- [x] InboundMsg 增加 `image_url` 字段
- [x] generator 检测 image_url → 调 vlm 拿描述 → 拼进 user prompt
- [x] 朋友圈截图识别（产品 / 价格 / 数量 / 类型）
- [x] tests/test_vlm_client.py ≥5 用例（mock）

### S5 · 多模态：语音转文字（豆包/阿里 ASR）
**目标**：客户发语音 · AI 转文字后回复。
**验收**：
- [x] `server/asr_client.py` · 豆包 ASR API 包装（mock fallback）
- [x] InboundMsg 增加 `voice_url` 字段
- [x] inbound 检测 voice_url → 调 asr → 把转写文字塞 text 字段继续走流程
- [x] tests/test_asr_client.py ≥4 用例（mock）

### S6 · 反检测套件（防被识破是 AI）
**目标**：3 个防露馅机制：错别字池 + 开场变体 + 疑心检测。
**验收**：
- [x] `server/anti_detect.py` · 3 个工具：
  - `inject_typo(text, prob=0.05)` · 5% 概率插入轻微 typo（"的"→"得" / 同音字）
  - `vary_opening(text)` · 替换"亲，您好~"为 10 个变体之一
  - `detect_suspicion(text)` · 客户问"你是 AI 吗" / "怎么回这么慢" → 返 True
- [x] generator 集成：rewrite 后 → 反检测处理 → 输出
- [x] 检测到 suspicion → audit + 推老板 + 标记 review_required
- [x] tests/test_anti_detect.py ≥10 用例

### S7 · 交叉销售引擎
**目标**：基于客户档案 + 知识库 · 主动推相关产品。
**验收**：
- [x] `server/cross_sell.py` · `recommend(customer_profile, current_product) → list[ProductRec]`
- [x] 用 customer_profile.purchase_history + knowledge_base 召回相关品
- [x] 触发：客户表达兴趣（intent=ORDER · 等）→ 自动加推荐到回复
- [x] 风险控制：每对话最多 1 次交叉销售（不烦客户）
- [x] tests/test_cross_sell.py ≥6 用例

### S8 · 朋友圈托管（AI 写文案 + 定时发）
**目标**：每天 AI 自动写 1-3 条朋友圈 · 模拟真人晒生活。
**验收**：
- [x] `server/moments_manager.py` · `generate_post(tenant, post_type) → str`
- [x] 4 种 post_type：产品晒图 / 用户反馈 / 限时活动 / 日常生活
- [x] 新表 `moments_posts`（draft/scheduled/published）
- [x] APScheduler 每天 09:00/14:00/19:00 自动写 + 走 ws push 让 client 发
- [x] API：`POST /v1/moments/{tenant}/draft` `GET /v1/moments/{tenant}` `POST /v1/moments/{post_id}/publish`
- [x] tests/test_moments.py ≥8 用例

---

## 三、不做的事（避免范围蔓延）

- ❌ 群聊管理（留 Third Wave）
- ❌ 真训练 LoRA（等 GPU + 50 客户）
- ❌ 行业飞轮（已撤销 · 不引入）
- ❌ Qt6 浮窗 prototype（全自动模式不需要）
- ❌ Sentry 部署（FDW 范围）

---

## 四、验收准则

1. pytest 271 + SDW ≥60 用例 → ≥330 全绿
2. 端到端 10 场景（拟人节奏 + 心理学触发 + 行业适配 + 图片识别 + 反检测）
3. 0 个 TODO/FIXME · 0 个 mock 散落
4. MISSION/ARCHITECTURE/STATUS_HANDOFF 同步到 v5
5. 真接通 Qwen3-VL + 豆包 ASR API（mock fallback · 真路径连大哥发 key）

---

## 五、外部依赖（不阻塞 macOS 验收）

| 资源 | 谁提供 | 卡哪个功能 |
|---|---|---|
| Qwen3-VL API key | 连大哥（阿里云百炼）| S4 真识图 |
| 豆包 ASR key | 连大哥（火山引擎）| S5 真转语音 |
| Windows + 微信账号 | 连大哥 | S1 typing 真发 / S8 朋友圈真发 |
