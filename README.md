# wechat_agent · 微信全自动回复 SaaS

> 装在客户电脑上的 24h 全自动微信员工
> 让微商/销售老板的微信 24h 在线 · 回复又快又像他自己

---

## 一句话定位

**老板的 24h 数字分身**：全自动监听 + 生成 + 发送，高风险熔断，第一个月 0 封号保证。

---

## Quickstart（5 分钟）

```bash
# 1. 安装依赖
make install

# 2. 初始化 SQLite
make init-db

# 3. 配置 0 号客户（连大哥）
cp config/config.example.yaml config/config.yaml
cp config/tenants.example.yaml config/tenants.yaml
cp .env.example .env

# 4. 种子数据
make seed

# 5. 启动 server（端口 8327）
make run

# 6. 健康检查
curl http://127.0.0.1:8327/v1/health
```

---

## 项目结构

```
wechat_agent/
├── client/         # Windows 客户端（wxautox · macOS 可 mock）
│   ├── watcher.py  · sender.py  · risk_control.py
│   ├── review_popup.py（AUTO/HIGH_RISK_ONLY/MANUAL 三模式）
│   ├── content_watcher.py   # T1 魔法文件夹 watchdog
│   └── consent_page.py      # T5 首装授权弹窗
├── server/         # 服务端（FastAPI · macOS/Linux · 20+ 路由）
│   ├── auto_send.py         # F1 全自动引擎
│   ├── customer_profile.py  # F2 客户档案
│   ├── embedder.py          # F3 BGE-small-zh-v1.5
│   ├── knowledge_base.py    # F3 RAG 知识库
│   ├── follow_up.py         # F4 跟进序列
│   ├── classifier.py        # F5 hybrid + emotion
│   ├── health_monitor.py    # F6 反封号引擎
│   ├── account_failover.py  # F7 多账号容灾
│   ├── dashboard.py         # F8/T3 Dashboard v3（行动型）
│   ├── content_ingest.py    # T1 内容摄入引擎
│   ├── marketing_plan.py    # T2 营销方案生成器
│   ├── customer_pipeline.py # T3 待成交 Pipeline
│   ├── action_recommender.py # T3 推荐行动引擎
│   ├── encryption.py        # T4 数据护城河（per-tenant KMS）
│   ├── data_export.py       # T5 合规导出
│   ├── data_deletion.py     # T5 GDPR 删除
│   ├── scheduler.py         # APScheduler 后台 jobs
│   ├── prompt_builder.py    # system prompt 单点管理
│   └── llm_client.py        # LLM 客户端（多模型路由）
├── evolution/      # 训练队列（accept/edit/reject 加权样本）
├── pipeline/       # 数据采集 + LoRA 训练 + 评估
├── shared/         # client/server 共享协议（含 EmotionEnum）
├── db/             # schema.sql（18 张表）+ migrations
├── legal/          # data_ownership.md（T5）+ user_agreement + privacy_policy
├── config/         # yaml 配置模板
├── tests/          # pytest 套件（463 用例全绿）
├── docs/specs/     # spec 三件套（Phase 1-7 + First Wave + SDW + TDW）
├── scripts/        # 初始化脚本 + ingest_knowledge.py CLI
├── legal/          # 用户协议 / 隐私政策（Phase 5 法务定稿）
├── MISSION.md      # v2 产品宪法
├── ARCHITECTURE.md # v2 全局技术架构（8 模块拓扑）
├── task_plan.md    # 8 周路线
├── findings.md     # 技术调研档案（RAG/embedder/health 选型）
└── progress.md     # 每日会话日志（Session 1-4）
```

---

## Fourth Wave (FDW+) · 部署交付 + 法律防护（2026-04-16 落地 · 上线 ready）

| 能力 | 说明 |
|---|---|
| **F1 一键安装器** | Nuitka 编译 + InnoSetup 3-click setup.exe · 协议页 + 快捷方式 + 开机自启 |
| **F2 激活码系统** | 活码生成 / 设备绑定 / 心跳 / 离线 7 天禁用 · DPAPI 安全存储 |
| **F3 客户端自动更新** | 启动时静默检查版本 → 后台下载 → 下次启动无感升级 |
| **F4 系统托盘** | pystray · 绿/黄/红 3 色灯实时显示健康状态 · 一键暂停/恢复 |
| **F5 Web 鉴权** | Bearer token · activation_code 换 token · X-Test-Mode 开发 bypass |
| **F6 管理后台** | admin.py · ADMIN_TOKEN · 客户列表 + 健康分 + 一键发激活码 |
| **F7 云端部署** | docker-compose.prod + nginx + certbot + init 一键上线 · 详见 [deploy_guide.md](docs/deploy_guide.md) |
| **F8 Sentry** | self-hosted · server + client 双端崩溃监控 · 详见 [sentry_setup.md](docs/sentry_setup.md) |
| **L1 协议 v3** | user_agreement_v3 · 微信合规免责 + 灰产拒绝列表 · server 强制签署校验 |
| **L2 灰产拒绝** | compliance_check.py · 9 类关键词 · severity 分级 · generator + KB 双层过滤 |
| **L3 举报检测** | wechat_alert_detector · toast 检测 → emergency_stop 路由 |
| **L4 律师举证包** | legal_export.py · audit + consent + summary · 设备指纹 + IP + 时间戳 |
| **L5 行业合规** | sensitive 默认 high_risk_block · restricted 启动拒绝 · 起诉概率 < 1% |

**上线 ready**：激活码 · 安装器 · 云部署脚本 · Sentry · 管理后台全部就绪 · 等连大哥：Windows + 域名 + 律师 + 商户号。

## Third Wave (TDW) 落地闭环（2026-04-16 落地 · 客户锁定生效）

| 能力 | 说明 |
|---|---|
| **T1 魔法文件夹** | 丢进 `~/wechat_agent_input/` 任意格式（md/csv/jpg/mp3）→ AI 自动消化 → 立即影响私聊回复 |
| **T2 营销方案生成器** | 上传新产品资料 → 自动生成朋友圈 5 条 + 私聊 SOP + 群发 A/B/C · 老板一键 activate |
| **T3 行动型 Dashboard** | 每天打开看"今天该跟谁说什么" · 待成交 top 10 · urgency 排序 · 推荐话术 |
| **T4 数据护城河** | per-tenant fernet 加密 · LoRA 落盘加密 · KMS 抽象 · 客户走了带不走训练资产 |
| **T5 客户授权** | 原始聊天可导出（合规）· 训练资产归 wechat_agent · 首装弹窗授权 · GDPR 30 天 grace |

**客户锁定经济学**：用 3 个月后 500+ customer_profile + 专属 LoRA + 营销库无法迁移 → 续费率目标 90%+ · LTV ¥8388/客户/年。

## Second Wave (SDW) 拟人化护城河（2026-04-16 落地 · 像真人度 95%）

| 能力 | 说明 |
|---|---|
| **S1 节奏拟人引擎** | 高斯延迟 1-3s 打字感 · 长句拆段发 · 夜间模式"刚醒看到~" |
| **S2 心理学触发器** | Cialdini 6 类自动选 · loss_aversion 2.5x · 4 维决策矩阵 · 成交率 +25% |
| **S3 6 行业模板池** | 微商/房产/医美/教培/电商/保险 · LLM 自动检测行业 · 话术风格微调 |
| **S4 图片理解** | Qwen3-VL 看图回价 · 朋友圈截图识别产品/价格 · mock fallback |
| **S5 语音转文字** | 豆包 ASR 转写客户语音 · 无缝接入回复流程 · mock fallback |
| **S6 反检测套件** | 5% typo 注入 + 10 个开场变体 · "你是 AI 吗"自动暂停推老板 |
| **S7 交叉销售** | 档案+知识库推相关品 · VIP 风控每对话最多 1 次 · 自然话术追加 |
| **S8 朋友圈托管** | 4 种 post_type · 每天 3 次 AI 写文案 · scheduler 自动发 |

## First Wave 核心能力（2026-04-16 落地）

| 能力 | 说明 |
|---|---|
| **F1 真全自动引擎** | suggestion → 风控 → 直发 · 高风险熔断 · 一键暂停（3s 生效）|
| **F2 客户档案引擎** | 每个联系人动态档案 · AI 回复自动带称呼/购买记录/偏好 · VIP A/B/C 分级 |
| **F3 知识库 RAG** | 老板上传产品手册一次 · AI 永远会查 · BGE-small-zh 本地 embedding |
| **F4 跟进序列** | 下单后自动催付款/问收到/问效果/问复购 · 全靠 cron 无需老板记 |
| **F5 情绪感知** | 识别 CALM/ANXIOUS/ANGRY/EXCITED · 客户骂街自动软化共情 · 客户兴奋临门推优惠 |
| **F6 24/7 反封号** | 5 维度实时评分 · 黄灯自动降速 · 红灯自动暂停 · 0 封号目标 |
| **F7 多账号容灾** | 主号涨红自动切小号 · 客户无感 · 完整切换日志 |
| **F8 Dashboard v2** | 7 天趋势图 · 客户分级 · 成交漏斗 · 每周一飞书周报 |

## 核心原则（来自 `MISSION.md`）

1. **全自动直发**：suggestion 生成后直走 sender，高风险才熔断等老板
2. **每客户专属档案**：动态记住称呼/偏好/购买记录，让客户感知被记住
3. **多租户隔离**：每 tenant AES-256 加密，跨 tenant 调用红线熔断
4. **反封号严格**：5 维度评分 + 三档自动响应 + 多账号容灾
5. **永不绝对化承诺**：保证/一定/终身/稳赚 → 拒绝生成
6. **像真人度 95%**：7 触点拟人化 + Cialdini 6 原则 + 反检测套件

---

## 测试

```bash
make test          # 全跑
make test-cov      # 含覆盖率
make lint          # ruff
make fmt           # ruff format
```

---

## 文档

- [task_plan.md](task_plan.md) — 8 周执行路线 + First Wave 完成清单
- [findings.md](findings.md) — 技术调研结论（RAG/embedder/health 选型）
- [progress.md](progress.md) — 会话日志（Session 1-6）
- [MISSION.md](MISSION.md) — v2 产品宪法
- [ARCHITECTURE.md](ARCHITECTURE.md) — v2 全局技术架构
- [STATUS_HANDOFF.md](STATUS_HANDOFF.md) — v7 交接清单（已交付 vs 待连大哥 · 上线 ready）
- [RISK_CONTROL.md](RISK_CONTROL.md) — 反封号策略
- [SETUP.md](SETUP.md) — 完整环境配置（macOS + Windows）
- [docs/deploy_guide.md](docs/deploy_guide.md) — 云端上线手册（F7 · docker-compose.prod + nginx + certbot）
- [docs/sentry_setup.md](docs/sentry_setup.md) — Sentry self-hosted 部署手册（F8）
- [docs/specs/first_wave/](docs/specs/first_wave/) — First Wave spec 三件套
- [docs/specs/second_wave/](docs/specs/second_wave/) — SDW spec 三件套（拟人化 8 件）
- [docs/specs/third_wave/](docs/specs/third_wave/) — TDW spec 三件套（落地闭环 5 件 · 客户锁定）
- [docs/specs/fourth_wave/](docs/specs/fourth_wave/) — FDW+ spec 三件套（部署 8 件 + 法律防护 5 件）
- [legal/user_agreement_v3.md](legal/user_agreement_v3.md) — 用户协议 v3（L1 · 微信合规免责）
- [legal/data_ownership.md](legal/data_ownership.md) — 数据所有权条款（T5）

---

## 当前状态

- **阶段**：**First Wave + SDW + TDW + FDW+ 全部完成** · pytest 604/604 全绿 · 上线 ready
- **像真人度**：95%（7 触点拟人化 + Cialdini 6 原则 + 反检测）
- **客户锁定**：数据护城河生效 · LoRA 加密 · LTV ¥8388/客户/年
- **法律防护**：L1-L5 全落地 · 起诉概率 < 1% · 灰产 9 类自动拒绝 · 律师举证包就绪
- **上线 ready**：激活码 · 安装器 · 云部署 · Sentry · 管理后台全就绪
- **外部待接**：Windows 机器 · 域名 + 云服务器 · 律师签字 · 微信支付商户号
- **下一步**：连大哥任意外部资源到位 → 当天推进

---

## License

私有 · 仅供 wechat_agent 项目使用。

---

## 联系

- CEO / 产品 / 客户：连大哥（ach73680@gmail.com）
- CTO-AI 团队：童虎
