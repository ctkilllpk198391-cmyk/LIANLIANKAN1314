# Second Wave (SDW) · Tasks

> feature_id: `second_wave`
> 完成标准：所有 [x] + 端到端 10 场景过 + pytest ≥330 全绿

---

## 批次 A · Day 0-3 · 核心拟人 · 独立强并行

### A1 · S1 节奏拟人引擎
- [ ] server/typing_pacer.py 高斯延迟算法
- [ ] server/message_splitter.py 长句拆段
- [ ] WS payload 增加 segments[] · auto_send.py 改造
- [ ] tenant config pacing_enabled / nighttime_off
- [ ] tests/test_typing_pacer.py ≥6 用例
- [ ] tests/test_message_splitter.py ≥6 用例

### A2 · S2 心理学触发器
- [ ] server/psych_triggers.py 6 类触发器 + 决策矩阵
- [ ] customer 阶段识别（explore/compare/near/post_buy/dormant）
- [ ] prompt_builder.py 集成 psych_block
- [ ] tests/test_psych_triggers.py ≥12 用例

### A3 · S6 反检测套件
- [ ] server/anti_detect.py inject_typo + vary_opening + detect_suspicion
- [ ] generator.generate 末尾集成
- [ ] main.py inbound 检测 suspicion → 暂停 + 推老板
- [ ] tests/test_anti_detect.py ≥10 用例

### A4 · S3 行业模板池（subagent · sonnet）
- [ ] server/industry_templates/{微商,房产,医美,教培,电商,保险}.md 6 个
- [ ] server/industry_router.py 加载 + 检测
- [ ] tenant config industry 字段
- [ ] prompt_builder.py 集成 industry_block
- [ ] tests/test_industry_router.py ≥6 用例

---

## 批次 B · Day 3-6 · 业务深度 · 派 sonnet 并行

### B1 · S7 交叉销售引擎（subagent · sonnet）
- [ ] server/cross_sell.py CrossSellEngine + ProductRec
- [ ] 用 customer_profile.purchase_history + knowledge_base 召回
- [ ] generator 后处理：调 maybe_append_to_reply
- [ ] 风控：每客户每天最多 1 次 + 投诉时不推
- [ ] tests/test_cross_sell.py ≥6 用例

### B2 · S8 朋友圈托管（subagent · sonnet）
- [ ] schema/models.py 加 moments_posts 表 + ORM
- [ ] server/moments_manager.py 4 种 post_type 生成
- [ ] scheduler 注册：每天 09/14/19 时 tick
- [ ] API：POST /v1/moments/{tenant}/draft · GET list · POST publish
- [ ] tests/test_moments.py ≥8 用例

---

## 批次 C · Day 6-9 · 多模态 · 派 sonnet 并行

### C1 · S4 图片理解（subagent · sonnet）
- [ ] server/vlm_client.py QwenVL API + mock fallback
- [ ] InboundMsg 加 image_url 字段
- [ ] main.py inbound 检测 type=image → 调 vlm
- [ ] tests/test_vlm_client.py ≥5 用例（mock）

### C2 · S5 语音转文字（subagent · sonnet）
- [ ] server/asr_client.py 豆包 ASR + mock fallback
- [ ] InboundMsg 加 voice_url 字段
- [ ] main.py inbound 检测 type=voice → 调 asr → 替换 text
- [ ] tests/test_asr_client.py ≥4 用例（mock）

---

## 批次 D · Day 9-11 · 集成 + 端到端

### D1 · main.py 全集成
- [ ] inbound 接入：S4 vlm → S5 asr → S2 psych → S6 anti_detect → S7 cross_sell → S1 pacer
- [ ] 拼接 4 个 prompt block：customer + knowledge + industry + psych
- [ ] auto_send.py 改 trigger_send 推 segments[]
- [ ] 跑全 pytest 全绿（≥330）

### D2 · 端到端 10 场景
- [ ] tests/e2e/test_second_wave_e2e.py 10 个场景
- [ ] 节奏 / 心理学 × 2 / 行业 / 图片 / 语音 / 反检测 × 2 / 交叉销售 / 朋友圈

### D3 · 文档同步 v5
- [ ] STATUS_HANDOFF.md v5（SDW 完成 · 模块清单 · 测试数）
- [ ] progress.md 加 Session 4
- [ ] task_plan.md 标 SDW 完成
- [ ] findings.md 加 § 12 拟人化 7 触点 + Cialdini 6 原则

### D4 · 启动验收
- [ ] uvicorn 启动 · curl 新路由
- [ ] grep TODO/FIXME = 0
- [ ] aivectormemory 记忆 3 条（SDW 完成 / 节奏算法 / 决策矩阵）

---

## 不做的事
- ❌ 群聊管理（留 Third Wave）
- ❌ 真训练 LoRA（等 GPU + 50 客户）
- ❌ 视频识别 / 直播流（不在范围）
