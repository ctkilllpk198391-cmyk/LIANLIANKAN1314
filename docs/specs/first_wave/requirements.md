# First Wave · 8 件功能 + 6 件清理 · Requirements

> 立项日期：2026-04-16
> 立项人：连大哥 · 童虎执行
> 周期：11.5 工作日（macOS 全跑通 · Windows 真测等连大哥接机）
> 目标：兑现"24h 全自动微信员工"产品力 · 让客户用 30 天后无法离开

---

## 一、产品定位（决策已定）

- **技术内部**：24h 全自动监听 + 生成 + 发送 · 不需要老板参与
- **营销外壳**：AI 副驾驶辅助 · 用户协议写"辅助工具，最终由本人决定"
- **合规兜底**：高风险消息熔断 + 手机端紧急一键暂停 + 反封号自动调速
- **客户感知**：装好就跑 · 像他自己在回 · 数据上瘾

---

## 二、8 件功能 · 验收标准

### F1 · 真全自动引擎
**目标**：suggestion 生成后默认直发 · 不进审核队列 · 老板只在异常时介入。
**验收**：
- [x] `auto_send` 配置项 · tenant 级别开关（默认 `true`）
- [x] suggestion 生成后 → risk=high → 熔断不发 · 推老板手机通知
- [x] suggestion 生成后 → risk=low/medium → 直接走 sender
- [x] 紧急一键暂停 API（`POST /v1/control/{tenant}/pause`）· 3 秒内停所有自动行为
- [x] audit log 完整：auto_send_enabled / risk_blocked / paused_by_boss
**反例**（要拒绝）：浮窗强制审核、超过 5 秒还在等老板按发送键

### F2 · 客户档案引擎（customer_profile）
**目标**：每个 contact 一份动态档案 · AI 回复时引用 · 让客户感知"被记住"。
**验收**：
- [x] 新表 `customer_profiles`：tenant_id + chat_id + 称呼/购买记录/敏感点/最后联系时间/标签/VIP 等级
- [x] 老客户来 → AI prompt 自动带"上次买过 X · 偏好 Y · 称呼 Z"
- [x] 自动累积：每次对话后 → background task 提取 + 更新档案
- [x] 新客户首次对话 → 创建空档案 → 后续累积
- [x] API：`GET /v1/customers/{tenant}/{chat_id}` 查档案 · `PATCH` 手动改
**反例**（要拒绝）：每次都重新问客户名字、忘记上次说过的事

### F3 · 产品/价格/库存知识库 RAG
**目标**：老板上传产品手册一次 · AI 永远会查 · 客户问参数立即准答。
**验收**：
- [x] 新表 `knowledge_chunks`：tenant_id + chunk_text + embedding (JSON list float) + source + tags
- [x] embedding 用本地 `BAAI/bge-small-zh-v1.5`（~100MB · macOS 跑得动）· numpy cosine
- [x] 摄入接口：`POST /v1/knowledge/{tenant}/ingest` · 接 markdown/txt/CSV · 自动切 chunk
- [x] generator 增加 RAG 召回：classify 后 → 召回 top 3 相关 chunk → 塞 system prompt
- [x] 查询接口：`POST /v1/knowledge/{tenant}/query` · 返回 top 3 chunks
**反例**（要拒绝）：让客户重复填问卷、产品参数从 prompt 里硬编码

### F4 · 跟进序列引擎（follow_up）
**目标**：老板睡觉时 AI 自动催付款 / 跟订单 / 提复购 · 全靠 cron。
**验收**：
- [x] 新表 `follow_up_tasks`：tenant_id + chat_id + task_type + scheduled_at + status + template_id
- [x] 4 种 task_type：未付款 30 分钟提醒 / 已付款 1 天问收到 / 7 天问效果 / 30 天问复购
- [x] 触发：order intent 识别 → 自动创建 follow-up task
- [x] APScheduler 每分钟扫一次 · 到点 → generator 生成跟进文案 → 走 sender
- [x] API：`GET /v1/follow_up/{tenant}` 查队列 · `DELETE /v1/follow_up/{task_id}` 取消
**反例**（要拒绝）：客户付款后老板手动催发货、复购全靠老板记忆

### F5 · 意图升级（7 类细粒度 + 4 类情绪）
**目标**：classifier 从 rule mode 升级到 hybrid mode · 加情绪维度 · 走最优策略。
**验收**：
- [x] hybrid 模式：rule 先跑 · confidence < 0.6 → fallback LLM
- [x] 新增 `EmotionEnum`：CALM / ANXIOUS / ANGRY / EXCITED
- [x] `IntentResult` 增加 `emotion` 字段
- [x] LLM 模式 prompt：让 DeepSeek 同时返回 intent + emotion
- [x] generator system prompt 根据 emotion 自动调语气：ANGRY → 软化共情 / EXCITED → 临门推优惠
**反例**（要拒绝）：客户骂街还回"亲~"、客户兴奋还机械应答

### F6 · 24/7 反封号引擎（health_monitor）
**目标**：5 维度监控账号健康 · 异常自动降速/暂停 · 第一个月 0 封号。
**验收**：
- [x] 新表 `account_health_metrics`：tenant_id + chat_id + dim_name + value + recorded_at
- [x] 5 个维度：好友通过率 / 消息相似度均值 / 客户回复率 / IP 切换次数 / 心跳异常
- [x] 每 5 分钟评分 · `health_score` 0-100
- [x] 三档自动响应：80+ 正常 / 60-80 黄灯（日配额砍半 + 单聊间隔 ×2）/ <60 红灯（暂停 1 小时）
- [x] API：`GET /v1/health/{tenant}` 实时分数 · `POST /v1/health/{tenant}/recover` 手动恢复
**反例**（要拒绝）：账号已经红灯还在硬发、降速但不通知老板

### F7 · 多账号容灾（account_failover）
**目标**：一个老板有多个微信号 · 主号涨红 → 自动切小号 · 客户无感知。
**验收**：
- [x] tenants schema 增加 accounts 字段（JSON list · primary + secondaries）
- [x] sender 根据当前 active_account_id 选号
- [x] health_monitor 红灯触发 → 自动切下一个健康账号 · 推老板通知
- [x] 切换记录：新表 `account_failover_log`
- [x] API：`GET /v1/accounts/{tenant}` 查所有号状态 · `POST /v1/accounts/{tenant}/switch/{account_id}` 手动切
**反例**（要拒绝）：单号挂了整个客户瘫痪、切换记录丢失

### F8 · Dashboard 升级
**目标**：老板每天打开 = 心理上瘾 = 续费率拉满。
**验收**：
- [x] 增加 7 天采纳率趋势线（accept/edit/reject 分类）
- [x] 增加客户分级：A（VIP · 月成交 ≥3）/ B（活跃 · 月对话 ≥5）/ C（沉睡 · 30 天未联系）
- [x] 增加成交漏斗：询价 → 砍价 → 下单 → 复购 各阶段转化率
- [x] 增加同行对标：你的成交率 vs 行业均值（先用静态基线 65% · Phase 7 替换聚合）
- [x] 周报自动飞书推送（cron 每周一 09:00）· 接口预留
- [x] 已有 `server/templates/dashboard.html` 重写成趋势图（用 chart.js CDN）
**反例**（要拒绝）：只显示今日数字、看不出趋势、看不出哪个客户该重点跟

---

## 三、6 件清理动作（边做边清）

### C1 · `server/hermes_bridge.py` → `server/llm_client.py`
理由：`hermes_bridge` 是 whale_tracker 残留命名 · 内部已经直连 LLM API · 改名归位。

### C2 · 删 `evolution/industry_flywheel.py` → 新建 `evolution/training_queue.py`
理由：industry_flywheel 是论文级 STELLA/差分隐私聚合 · 早期没数据没必要。
training_queue 做的事：每次 review 决策（accept/edit/reject）→ 写入训练队列 → Phase 2 LoRA 触发时全量导出。

### C3 · 重写 `wechat_agent/MISSION.md`（v2）
- 删掉所有"白羊/紫龙/童虎/HERMES 实例克隆/师徒/STELLA/AutoMaAS/8 Swarm"
- 改成纯产品宪法：我们是谁 / 为谁服务 / 三硬约束 / 五 KPI / 价值观
- 全自动 + 副驾驶外壳 写进宪法（避免下次又被改回去）

### C4 · 重写 `wechat_agent/ARCHITECTURE.md`（v2）
- 删 `hermes-agent:8317` 依赖
- 数据流图按"全自动直发 + 高风险熔断"重画
- 增加新表（customer_profiles / knowledge_chunks / follow_up_tasks / health_metrics / accounts / training_queue）
- 8 模块拓扑图

### C5 · 新建 `wechat_agent/CLAUDE.md`（项目专属规则）
- 项目背景 + 核心定位
- 关键文件指引
- 不再混淆 whale_tracker

### C6 · 删 `client/review_popup.py` 强制审核逻辑 → 改成可选浮窗（默认关）
- 全自动模式下浮窗不弹
- 仅高风险消息或老板手动开启时弹

---

## 四、不做的事（避免范围蔓延）

- ❌ 朋友圈托管（30 件功能里 · 留到第二波）
- ❌ 群聊管理（同上）
- ❌ 图片理解（Qwen3-VL · 等真客户有需求再接）
- ❌ STELLA / AutoMaAS / Alignment Check / 8 Swarm（已撤销 · 永不引入）
- ❌ Qt6 浮窗 prototype（全自动模式不需要 · 节省 1 天工时）
- ❌ 真训练 LoRA（等 GPU + 50 客户）
- ❌ vLLM 多 LoRA 部署（同上）
- ❌ Sentry self-hosted（等 5 客户后）

---

## 五、验收准则

1. **pytest 全绿**：现有 149 用例 + First Wave 新增 ≥40 用例 → ≥189 全绿
2. **端到端真路径**：6 场景（陌生新客 / 老客复购 / 客户砍价 / 客户投诉 / 客户下单跟单 / 长尾询价）走完整流程 · 采纳率 ≥80%
3. **数据库迁移**：alembic 脚本 + db/schema.sql 同步更新 · `make init-db` 不报错
4. **0 个 TODO/FIXME**：新代码不留 stub · mock 数据有兜底
5. **文档同步**：MISSION.md / ARCHITECTURE.md / STATUS_HANDOFF.md 全部更新到 v3

---

## 六、外部依赖（不阻塞 macOS 验收）

| 资源 | 谁提供 | 卡哪个功能 |
|---|---|---|
| Windows + 微信账号 | 连大哥 | F1/F6/F7 真桌面验证 |
| 飞书机器人 webhook | 连大哥 | F8 周报推送（先 mock） |
| GPU 12GB+ | 连大哥 | C2 training_queue 真训练（队列写入不依赖） |
| BGE 模型 100MB | 童虎下载 | F3 RAG embedding |
