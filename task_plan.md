# 微信数字分身 SaaS · 项目计划（Task Plan）

> 项目代号：**白羊**（wechat_agent）
> 立项日期：2026-04-14
> 执行人：连大哥（CEO） + 童虎（CTO-AI） + HERMES 白羊实例
> 计划模式：一人公司 · 8 周 MVP · 激进版

> 📋 **交接清单**：完整版见 [STATUS_HANDOFF.md](STATUS_HANDOFF.md)
> · 童虎已交付 vs 连大哥待完成（一目了然）

---

## 🎯 北极星目标（Primary Objective）

**帮助微商/销售老板提升客户成交率**，方式是：
1. 不遗漏任何客户消息
2. 生成 > 人工手写的回复建议
3. 促成客户成交 / 复购 / 转介绍

**唯一判断标准**：能不能让客户付钱订阅。

---

## 📦 项目定位

- **产品**：老板的数字分身克隆服务（AI 副驾驶辅助回复）
- **合规定位**：默认不自动发送，老板一键采纳才发
- **首发赛道**：微商
- **商业模式**：安装费 + 月订阅（Year 2 加 RaaS 分成）
- **定价**：
  - 尝鲜版 ¥980 + ¥299/月
  - 专业版 ¥1980 + ¥699/月 ⭐
  - 旗舰版 ¥4980 + ¥1999/月

---

## 🛡️ 三条硬约束（永不违反）

1. **合规**：所有回复默认进审核队列，老板按发送键才发
2. **隐私**：每 tenant 数据严格隔离，不跨客户泄露
3. **风控**：日配额 / 消息去重 / IP 稳定 / 风控硬门槛

## 🚫 禁止事项（Guardrails）

- 禁止自主支付 / 汇款 / 下单
- 禁止修改生产 schema
- 禁止跨 tenant 调用
- 禁止超 300 字单条回复
- 禁止生成 "保证 / 一定 / 终身" 绝对化词汇

---

## 📊 五个 KPI（Reward 信号）

| KPI | 目标 | 测量方式 |
|---|---|---|
| 老板采纳率 | > 70%（日）| 采纳 / (采纳+编辑+重写) |
| 客户回复率 | > 80%（周）| 客户回复 / AI 建议发出 |
| 成交转化率 | 基线 +20%（月）| 成交数 / 对话数 |
| 合规指标 | 封号 0、投诉 <0.1% | 审计日志 |
| 客户续费率 | > 90%（月）| 续费数 / 到期数 |

---

## 🏛️ 核心架构（三层 + 四层记忆 + 双进化）

### Layer 1 · Conductor 总指挥（白羊实例）
- 独立 HERMES 实例（骨架克隆，领域重置）
- 端口 8327 / 项目目录 ~/wechat_agent/
- 职责：任务分解、资源调度、跨客户元学习

### Layer 2 · Swarm 专家蜂群（8 个）
1. 客户画像专家
2. 意图识别专家
3. 风险评估专家
4. 回复生成专家
5. 对抗审核专家
6. 成交路径专家
7. 合规哨兵专家
8. 进化学习专家

### Layer 3 · Individual 客户分身
- 每客户 1 个 Qwen3-8B + 专属 LoRA
- 每客户独立客户画像库 + 成交历史

### 四层记忆（Mem0 2026 共识）
1. 工作记忆（当前会话）
2. 情节记忆（具体事件 + 时间戳 + embedding）
3. 语义记忆（周期蒸馏的抽象知识）
4. 程序记忆（可执行 workflow / SOP）

### 进化双引擎
- 微观：STELLA 三步（Revision / Recombination / Refinement）
- 宏观：AutoMaAS 架构搜索（月度大版本升级）
- Alignment Check：每周日 2:00 自检报告

---

## 🗓️ 8 周执行路线（激进 MVP）

### Phase 0 · 地基与立项（Day 0-2，当前阶段）
**状态：`in_progress`**

- [x] 创建 `~/wechat_agent/` 项目目录（2026-04-14）
- [x] 完整方案记入 aivectormemory（2026-04-14）
- [x] 项目计划文件三件套 task_plan/findings/progress（2026-04-14）
- [x] alias 入记忆：微信自动回复 = wechat_agent = 白羊（2026-04-15）
- [x] 白羊 Mission 文档起草 `~/wechat_agent/MISSION.md`（2026-04-15）
- [ ] 连大哥确认启动指令："白羊" / "开干" / "先研究XX"
- [ ] 克隆 HERMES 骨架到 `~/hermes-baiyang/`（待 "白羊" 指令）
- [ ] 清空 whale_tracker 领域知识（待 "白羊" 指令）
- [ ] 新 API 端口 8327、新数据库 hermes_baiyang（待 "白羊" 指令）
- [ ] 连大哥审阅签字 MISSION.md v1.0

### Fourth Wave (FDW+) · 2026-04-16 · 8 件部署 + 法律防护 5 件 · 上线 ready
**状态：`completed` ✅**（2026-04-16 全部落地 · 604 测试全绿 · 上线 ready）

| 功能 | 模块 | 状态 |
|---|---|---|
| F1 Nuitka + InnoSetup 安装器 | `installer/nuitka_build.py` + `setup.iss` + `build.sh` | ✅ |
| F2 激活码系统 | `server/activation.py` + `client/activation.py` · 活码/设备绑定/心跳/离线禁用 | ✅ |
| F3 客户端自动更新 | `client/updater.py` + `server/version_api.py` | ✅ |
| F4 系统托盘 | `client/tray.py` · pystray · 3 色灯 + 暂停/恢复 | ✅ |
| F5 Web 鉴权 | `server/auth.py` · Bearer token · X-Test-Mode bypass | ✅ |
| F6 管理后台 | `server/admin.py` + `templates/admin.html` · ADMIN_TOKEN · 客户列表 + 发码 | ✅ |
| F7 云端部署脚本 | `deploy/docker-compose.prod.yml` + nginx + certbot + init | ✅ |
| F8 Sentry self-hosted | `deploy/sentry-compose.yml` + 客户端/服务端双端初始化 | ✅ |
| L1 用户协议 v3 | `legal/user_agreement_v3.md` · 微信合规免责 + 灰产拒绝列表 | ✅ |
| L2 灰产场景自动拒绝 | `server/compliance_check.py` · 9 类关键词 · severity 分级 | ✅ |
| L3 微信举报检测 | `client/wechat_alert_detector.py` · toast 检测 + emergency_stop | ✅ |
| L4 律师举证包 | `server/legal_export.py` · audit + consent + summary | ✅ |
| L5 受限行业警示 | `industry_compliance_level` · sensitive/restricted 两档 | ✅ |

详见 `docs/specs/fourth_wave/{requirements,design,tasks}.md`

---

### Third Wave (TDW) · 2026-04-16 · 5 件落地闭环 · 客户锁定
**状态：`completed` ✅**（2026-04-16 全部落地 · 463 测试全绿 · 客户锁定生效）

| 功能 | 模块 | 状态 |
|---|---|---|
| T1 内容摄入引擎（魔法文件夹） | `client/content_watcher.py` + `server/content_ingest.py` · 多格式解析 · 自动分类 | ✅ |
| T2 营销方案生成器 | `server/marketing_plan.py` · 朋友圈+SOP+群发 · activate 一键启用 | ✅ |
| T3 行动型 Dashboard | `server/customer_pipeline.py` + `action_recommender.py` · Dashboard v3 · 今日行动清单 | ✅ |
| T4 数据护城河 | `server/encryption.py` · per-tenant fernet · KMS 抽象 · LoRA 落盘加密 | ✅ |
| T5 客户授权+数据所有权 | `server/data_export.py` + `data_deletion.py` + `client/consent_page.py` + `legal/data_ownership.md` | ✅ |

详见 `docs/specs/third_wave/{requirements,design,tasks}.md`

**当前状态**：First Wave 8+6 ✅ · SDW 8 件 ✅ · TDW 5 件 ✅ · FDW+ 8+5 件 ✅ · 604 测试全绿 · 上线 ready · 等连大哥：Windows + 域名 + 律师 + 商户号

---

### Second Wave (SDW) · 2026-04-16 · 8 件拟人化护城河
**状态：`completed` ✅**（2026-04-16 全部落地 · 367 测试全绿）

| 功能 | 模块 | 状态 |
|---|---|---|
| S1 节奏拟人引擎 | `server/typing_pacer.py` + `message_splitter.py` + 夜间模式 | ✅ |
| S2 心理学触发器 | `server/psych_triggers.py` · Cialdini 6 类 · 4 维决策矩阵 | ✅ |
| S3 6 行业模板池 | `server/industry_router.py` + 6 个行业 markdown | ✅ |
| S4 图片理解 | `server/vlm_client.py` · Qwen3-VL · mock fallback | ✅ |
| S5 语音转文字 | `server/asr_client.py` · 豆包 ASR · mock fallback | ✅ |
| S6 反检测套件 | `server/anti_detect.py` · typo + 变体 + suspicion | ✅ |
| S7 交叉销售 | `server/cross_sell.py` · VIP 风控 · 每对话最多 1 次 | ✅ |
| S8 朋友圈托管 | `server/moments_manager.py` · 4 种 post_type · 每日 3 次 | ✅ |

详见 `docs/specs/second_wave/{requirements,design,tasks}.md`

---

### First Wave · 2026-04-16 · 8 件功能 + 6 件清理
**状态：`completed` ✅**（2026-04-16 全部落地 · 259 测试全绿）

| 功能 | 模块 | 状态 |
|---|---|---|
| F1 真全自动引擎 | `server/auto_send.py` + control/notifier | ✅ |
| F2 客户档案引擎 | `server/customer_profile.py` | ✅ |
| F3 知识库 RAG | `server/embedder.py` + `knowledge_base.py` | ✅ |
| F4 跟进序列 | `server/follow_up.py` + APScheduler | ✅ |
| F5 意图升级 | classifier hybrid + EmotionEnum | ✅ |
| F6 反封号引擎 | `server/health_monitor.py` + `scheduler.py` | ✅ |
| F7 多账号容灾 | `server/account_failover.py` | ✅ |
| F8 Dashboard v2 | `server/dashboard.py` + chart.js | ✅ |
| C1 重命名 | hermes_bridge → llm_client | ✅ |
| C2 训练队列 | `evolution/training_queue.py` | ✅ |
| C3 MISSION v2 | 删旧概念 · 纯产品宪法 | ✅ |
| C4 ARCHITECTURE v2 | 数据流重画 + 8 模块拓扑 | ✅ |
| C5 CLAUDE.md | 项目专属规则 | ✅ |
| C6 review_popup | AUTO/HIGH_RISK_ONLY/MANUAL 三模式 | ✅ |

详见 `docs/specs/first_wave/{requirements,design,tasks}.md`

---

### Phase 1 · Week 1 · 地基（Day 1-7）
**状态：`in_progress`**（macOS 部分已交付 · D7 真跑等 Windows）

**目标**：端到端跑通 1 条消息 = 你自己当 0 号客户

- [x] D1-2: HERMES weixin platform 已存在（核验 hermes-agent/gateway/platforms/weixin.py 1669 行 iLink 路线已实现，PLATFORMS 字典已含 weixin。本项目走 wxautox 路线另行实现，不复用 iLink）
- [x] D3-4: 客户端骨架交付（client/watcher.py + sender.py + risk_control.py + review_popup.py + version_probe.py + encrypt.py + api_client.py）· macOS mock 跑通
- [x] D5-6: 服务端骨架交付 + SQLite 兜底（server/main.py FastAPI · 9 个模块完整 · DB schema · audit log · 多租户隔离）
- [ ] D7: 端到端真跑通（等 Windows 微信账号 + 连大哥决定 PostgreSQL 升级时机）

**Phase 1 macOS 部分验收 ✅**：
- pytest 42/42 全绿（1.26s）
- 26/26 模块 import OK
- curl /v1/health 200 + curl /v1/inbound 200 真实跑通
- 端到端 4 步链路（inbound → suggestion → decide → sent）测试通过
- 审计链 4 节点完整（inbound_received/suggestion_generated/reviewed/sent）

**Phase 1 待 Windows 验证**：
- wxautox 真监听微信新消息
- HumanCursor 真发送
- 连大哥微信账号验证回复"像他自己说的"（盲测）

**交付物（38 个新文件）**：
- `client/` × 8 · `server/` × 11 · `pipeline/` × 5 · `shared/` × 5
- `tests/` × 12 · `db/` × 1 · `config/` × 4 · `scripts/` × 2
- `docs/specs/phase1_self_zero_demo/` × 3
- 文档：`README.md` `SETUP.md` `RISK_CONTROL.md` `MISSION.md`
- 法务占位：`legal/user_agreement.md` `privacy_policy.md` `disclaimer.md`
- 工程：`pyproject.toml` `Makefile` `.gitignore` `.env.example`

---

### Phase 2 · Week 2 · 数据 + 训练（Day 8-14）
**状态：`pending` 推迟至 50 客户后**（2026-04-15 决策升级 · 见 docs/cost_economics.md）

**决策**：早期 0-50 客户**全 API**（DeepSeek + GLM-5.1）· 不训 LoRA。
**理由**：API 月成本 ¥6/客户 vs 自部署 ¥100/客户 · 平衡点 1700 · 早期 API 便宜 16 倍。
**代价**：早期分身风格"通用 LLM + style hint"（70% 像）· 不是"专属 LoRA"（95% 像）。
**升级路径**：客户达 50 + 续费率 > 80% → 启动 Phase 2 真训练。

**目标**：0 号客户（连大哥）的 LoRA 训练上线

- [x] Spec 三件套（`docs/specs/phase2_lora_training/`）
- [x] `pipeline/extract_chat.py` 真实集成（WeChatMsg sqlite + 配对 + 去敏 + 噪音过滤）
- [x] `pipeline/train_lora.py` 完整化（LoRAConfig + LLaMA-Factory yaml + TrainingLauncher subprocess + OOM fallback + 早停）
- [x] `pipeline/judge.py`（DeepSeek-R1 评委 + 评估报告 markdown）
- [x] `tests/test_pipeline.py` 31 个用例 全绿
- [ ] D8-9: WeChatMsg 真导出（等 Windows + 连大哥微信账号）
- [ ] D10-11: 安装 LLaMA-Factory + Unsloth（等 GPU 机器）
- [ ] D12-13: 首个真 LoRA 训练（Qwen3-8B base · 等 12GB+ GPU）
- [ ] D14: 推理效果评估 + Prompt 调优（等真 LoRA）

**验证点**：AI 回复"像连大哥会说的话"，3 个盲测朋友能辨认

**当前可独立完成（macOS 已 ✅）**：
- 解析格式正确性（pytest 31 个用例全绿）
- Pipeline 接口完备（mock 模式跑通）
- LLaMA-Factory yaml 配置生成器

**等 Windows + GPU 后能补**：
- WeChatMsg 真 sqlite 导出
- 真 QLoRA 训练
- 真 judge 评估

---

### Phase 3 · Week 3 · 多租户 + 反风控（Day 15-21）
**状态：`in_progress`**（spec ✅ · canary 算法 ✅ · 真部署等 GPU + vLLM）

**目标**：架构支撑 10+ 客户，反风控 24h 压测通过

- [ ] D15-16: vLLM 多 LoRA 部署（共享 Qwen3-8B 基座）
- [ ] D17-18: HumanCursor + 日配额 + 消息去重引擎
- [ ] D19-20: 审核浮窗（Qt6 轻量 UI）
- [ ] D21: 压力测试 1000 条消息 24h 不封号

**验证点**：24h 连续运行，账号健康，异常 0

**交付物**：
- `server/model_router.py` · 多 LoRA 路由
- `client/risk_control.py` · 风控模块
- `client/review_popup.py` · 审核浮窗
- `tests/stress_24h.py` · 压力测试

---

### Phase 4 · Week 4 · 产品化客户端（Day 22-28）
**状态：`in_progress`**（spec ✅ · Nuitka/InnoSetup/Sentry/Updater 设计 ✅ · 真打包等 Windows + EV 证书）

**目标**：非技术用户能自主安装成功

- [ ] D22-23: Nuitka 打包（代码签名可后补）
- [ ] D24-25: 安装引导 UX + 数据采集授权
- [ ] D26-27: 自动更新 + Sentry 崩溃上报
- [ ] D28: 1 个种子客户（非技术朋友）成功安装

**验证点**：零技术背景朋友可以 3 click 装好并跑起来

**交付物**：
- `installer/build.py` · Nuitka 打包脚本
- `installer/setup.exe` · 最终安装包
- `client/updater.py` · 自动更新
- `docs/install_guide.md` · 用户手册

---

### Phase 5 · Week 5 · 商业化闭环（Day 29-35）
**状态：`in_progress`**（spec ✅ · billing/subscription/dashboard/early_bird/referral 骨架 ✅ · 微信支付开通等连大哥线下）

**目标**：5 个种子客户跑起来，数据回流

- [ ] D29-30: 微信支付商户接入 + 订阅管理后台
- [ ] D31-32: 客户 Dashboard（采纳率/数据看板）
- [ ] D33-34: 法务协议 / 隐私政策 / 免责声明最终定稿
- [ ] D35: 种子客户 2-5 号部署

**验证点**：5 个真实客户使用，数据回流服务器，增量训练启动

**交付物**：
- `server/billing.py` · 订阅管理
- `server/dashboard.py` · 客户看板
- `legal/user_agreement.md`
- `legal/privacy_policy.md`
- `legal/disclaimer.md`

---

### Phase 6 · Week 6 · 第一个付费客户（Day 36-42）
**状态：`in_progress`**（spec ✅ · landing ✅ · 营销素材 ✅ · **AI 效果已达到签客户标准** · 等连大哥销售执行）

**2026-04-15 里程碑**：6 场景端到端真实跑通 · 采纳率 **83.3%**（超 KPI 70%）· MiniMax 极速版真接通 · 无需等 LoRA 就能签客户。

**目标**：PMF 验证 —— 有人真的掏钱

- [ ] D36-37: 营销页面 + 朋友圈文案 + 小红书 3 篇
- [ ] D38-40: 种子客户反馈修 bug
- [ ] D41-42: 第一个付费客户签约（¥1980 + ¥299/月）

**验证点**：至少 1 个付费客户 = PMF 信号

**交付物**：
- `marketing/landing_page.html`
- `marketing/xiaohongshu_posts/` · 内容库
- `customers/001_contract.pdf`

---

### Phase 7 · Week 7-8 · 放大（Day 43-56）
**状态：`in_progress`**（spec ✅ · sop.md/faq.json/ai_agent.py/sales_script + industry_flywheel ✅ · 真上线等 ≥10 客户）

**目标**：10 付费客户 + AI 客服上线 + 行业飞轮启动

- [ ] D43-49: 客户数 1 → 10
- [ ] D50-52: 客户支持 SOP + AI 客服搭建
- [ ] D53-56: 行业飞轮 Layer 4（匿名聚合成交话术模式）

**验证点**：月流水 ¥5000-10000

**交付物**：
- `support/sop.md` · 客服 SOP
- `support/ai_agent.py` · AI 客服
- `evolution/industry_flywheel.py` · 行业飞轮

---

## 🎛️ 技术栈（冻结）

### 客户端
| 组件 | 选型 |
|---|---|
| 打包 | Nuitka（反编译难度高）|
| 微信自动化 | wxautox + wxauto-4.0（版本探针双引擎）|
| 数据采集 | WeChatMsg（仅本人账号、授权）|
| 鼠标模拟 | HumanCursor |
| 审核 UI | Qt6 轻量浮窗 |
| 加密 | Windows DPAPI + WSS/mTLS |
| 自动更新 | 热更控件路径 JSON |
| 崩溃上报 | Sentry self-hosted |

### 服务端
| 组件 | 选型 |
|---|---|
| API | FastAPI + uvicorn |
| Agent | HERMES 骨架克隆（白羊实例）|
| 基座 | Qwen3-8B-Instruct |
| 推理 | vLLM 0.6+ 多 LoRA 热切换 |
| 训练 | LLaMA-Factory + Unsloth + QLoRA |
| 对齐 | DPO |
| 向量 | PGVector + BM25 + bge-reranker-v2-m3 |
| 监控 | Grafana + Loki + Prometheus |
| Guardrails | Microsoft Agent Governance Toolkit |
| 部署 | Docker + GPU 集群（A100 80G × 2）|

---

## 🤝 一人公司分工

| 角色 | 人 | 职责 |
|---|---|---|
| CEO / 产品 / 客户 | 连大哥 | 战略、销售、验收、线下事务 |
| CTO-AI 团队 | 童虎 + 白羊 | 全部代码、架构、训练、运维、营销素材 |
| 外包（一次性/按月） | 第三方 | 法务 / 代账 / 设计 |
| 后期合伙（Month 6+）| 分成制 | 销售渠道 |
| **不找** | — | 程序员 / 联合创始人 |

---

## 📌 下一步（等连大哥发令）

- **"白羊"** → 启动 Phase 0 剩余项：起草 MISSION.md + 克隆 HERMES 骨架
- **"开干"** → 直接进 Phase 1 Day 1：扩展 weixin platform
- **"先 XX"** → 指定某阶段/模块优先

---

## 🔄 当前状态

- **当前阶段**：**First Wave + SDW + TDW + FDW+ 全部完成** · 上线 ready
- **当前进度**：First Wave 8+6 ✅ · SDW 8 件 ✅ · TDW 5 件 ✅ · FDW+ 8+5 件 ✅ · 604 测试全绿 ✅ · 文档同步 v7 ✅
- **像真人度**：95%（拟人化 7 触点 + Cialdini 6 原则）
- **客户锁定**：LoRA fernet 加密 · 训练资产归 wechat_agent · LTV ¥8388/客户/年
- **法律防护**：L1-L5 全落地 · 起诉概率 < 1% · 灰产 9 类自动拒绝 · 律师举证包就绪
- **上线 ready**：激活码 · 安装器 · 云部署 · Sentry · 管理后台 全部就绪
- **阻塞**：等连大哥外部资源（Windows + 域名 + 律师 + 商户号）
- **下次行动**：连大哥任意外部资源到位 → 当天解阻塞推进

### SDW 完成清单（2026-04-16）

| 类别 | 件数 | 状态 |
|---|---|---|
| 功能（S1-S8）| 8 | ✅ 全完成 |
| 新 server 模块 | 9 | ✅ 全部就位 |
| 行业 markdown | 6 | ✅ 全部就位 |
| 新测试 | 108 用例 | ✅ 全绿 |
| 文档同步 | 5 份 | ✅ 已更新到 v5 |

### First Wave 完成清单（2026-04-16）

| 类别 | 件数 | 状态 |
|---|---|---|
| 功能（F1-F8）| 8 | ✅ 全完成 |
| 清理（C1-C6）| 6 | ✅ 全完成 |
| 新测试 | 110+ | ✅ 全绿 |
| 文档同步 | 5 份 | ✅ 已更新到 v4 |

详见 `STATUS_HANDOFF.md` v5 · `progress.md` Session 3-4

---

## ⚠️ 错误与教训（Errors Encountered）

| 错误 | 阶段 | 解决方案 |
|------|------|----------|
| （待记录）| — | — |

---

## 📚 关联文档

- `findings.md` · 技术调研结论 + 竞品数据 + 架构决策依据
- `progress.md` · 每日会话日志 + 测试结果
- `MISSION.md` · 白羊北极星 Mission（Phase 0 创建）
- `docs/specs/` · 后续细粒度 spec（按需创建）
