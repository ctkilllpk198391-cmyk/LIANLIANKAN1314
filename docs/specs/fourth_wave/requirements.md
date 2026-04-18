# Fourth Wave (FDW+) · 部署交付 + 法律防护 · Requirements

> 立项：2026-04-16 · 周期：9 工作日
> 目标：客户能装、能用、能付费 · 法律风险最低
> 完成后：第一个付费客户能立即收 ¥1980 安装费 + ¥299/月

---

## 一、12 件功能

### 🚀 FDW 部署交付 7 件（7 工作日）

#### F1 · Nuitka 打包脚本 + InnoSetup 安装器
- [x] `installer/nuitka_build.py` Python 编译脚本（生成 wechat_agent.exe）
- [x] `installer/setup.iss` InnoSetup 配置（3-click 装好 + 协议页 + 创建快捷方式 + 开机自启）
- [x] `installer/build.sh` Linux 构建脚本（macOS dev 准备 · Windows 真编译）
- [x] tests/test_installer_config.py（验证配置完整性）

#### F2 · 激活码系统
- [x] schema + models.py 加 `activation_codes` + `device_bindings` 表
- [x] `server/activation.py` · 生成激活码 / 激活 / 设备绑定 / 离线 7 天禁用
- [x] `client/activation.py` · 输码激活 → 拿 device_token 存 DPAPI
- [x] API：POST /v1/activation/generate · /activate · GET /status
- [x] tests/test_activation.py ≥10

#### F3 · 客户端自动更新
- [x] `client/updater.py` · 启动时检查 server /v1/version → 静默下载 → 下次启动应用
- [x] `server/version_api.py` · GET /v1/version 返回 latest + download_url + min_supported
- [x] tests/test_updater.py ≥4

#### F4 · 系统托盘 UI
- [x] `client/tray.py` · pystray 托盘（绿/黄/红灯 + 一键暂停/恢复 + 退出）
- [x] tests/test_tray.py ≥3（mock pystray）

#### F5 · 客户 Web Dashboard 鉴权
- [x] `server/auth.py` · token-based auth（client_token from activation）
- [x] dashboard /v1/dashboard/{tenant}/v3 加 Bearer token 校验
- [x] HTML 模板加登录页（输 activation_code → 换 token）
- [x] tests/test_auth.py ≥6

#### F6 · 管理后台
- [x] `server/admin.py` · 管理员接口（发激活码 / 看所有客户健康 / 导出报表）
- [x] admin auth（独立 ADMIN_TOKEN env）
- [x] templates/admin.html · 客户列表 + 健康分 + 一键发激活码
- [x] API：GET /admin/customers · POST /admin/issue_code · GET /admin/health
- [x] tests/test_admin.py ≥6

#### F7 · 云端部署脚本
- [x] `deploy/docker-compose.prod.yml` · server + postgres + redis + nginx
- [x] `deploy/nginx.conf` · HTTPS + WSS + LB
- [x] `deploy/certbot.sh` · Let's Encrypt 自动续证
- [x] `deploy/init.sh` · 一键初始化（init-db + seed admin）
- [x] `docs/deploy_guide.md` · 上线手册

#### F8 · Sentry self-hosted
- [x] `deploy/sentry-compose.yml` · sentry + postgres + redis
- [x] `client/sentry_init.py` · 客户端崩溃捕获
- [x] `server/sentry_init.py` · 服务端异常上报
- [x] `docs/sentry_setup.md`

---

### 🛡️ 法律防护 5 件（2 工作日）

#### L1 · 用户协议 v3 强化
- [x] `legal/user_agreement_v3.md` 完整中文协议（含微信合规免责 + 灰产拒绝 + 数据归属）
- [x] `legal/disclaimer_v3.md` 免责声明
- [x] client/consent_page.py 加载 v3 + 强制阅读
- [x] server 启动时校验 tenant 已签 v3（未签 → 拒绝服务）

#### L2 · 灰产场景自动拒绝
- [x] `server/compliance_check.py` · 检测灰产关键词（赌/色/诈骗/医诊/金融荐股/虚假宣传）
- [x] generator 集成：客户消息含禁词 → 不生成 · 转人工 + audit
- [x] knowledge_base.ingest 加禁词检测 → 拒绝灰产资料入库
- [x] tests/test_compliance_check.py ≥10

#### L3 · 微信举报检测
- [x] `client/wechat_alert_detector.py` · 监听微信窗口 toast / 警告对话框
- [x] 命中"被举报""违规""限制" → 立即停 sender + 推老板紧急通知
- [x] server `/v1/control/{tenant}/emergency_stop` 路由
- [x] tests/test_wechat_alert_detector.py ≥4

#### L4 · 完整操作日志（举证）
- [x] audit_log 加字段：`legal_evidence_payload`（JSON · 含 client_consent_version + auto_send_setting + ip_origin）
- [x] 每条 auto_send 记录"客户配置时间戳 + IP + 设备指纹"
- [x] `server/legal_export.py` · 导出指定 tenant 全量审计日志（律师举证用）
- [x] tests/test_legal_export.py ≥4

#### L5 · 受限行业警示
- [x] tenant config 加 `industry_compliance_level`（normal/sensitive/restricted）
- [x] sensitive（医美/教培/金融）→ 默认 high_risk_block=True · 强制人审
- [x] restricted（赌/色/诈）→ 启动时拒绝服务
- [x] consent_page 弹专属合规承诺（sensitive 行业额外签）
- [x] tests/test_industry_compliance.py ≥4

---

## 二、不做的事
- ❌ 真去注册个体工商户（连大哥线下）
- ❌ 真买 EV 证书（连大哥线下）
- ❌ 真做 ICP 备案（连大哥线下）
- ❌ AWS KMS 真接（Phase 5）
- ❌ 群聊 / 视频号 / RaaS（第五波）

---

## 三、验收准则
1. pytest 469 + FDW+ ≥50 用例 → ≥519 全绿
2. e2e 5 场景（激活码 / 自动更新 / 托盘 / Web 登录 / 灰产拒绝）
3. 0 个 TODO/FIXME · 0 个 mock 散落
4. 文档同步 v7：STATUS_HANDOFF + progress + task_plan + findings + README + 新建 deploy_guide
5. uvicorn 启动 + curl 新路由 + admin 后台访问

---

## 四、外部依赖
| 资源 | 谁 | 卡哪个 |
|---|---|---|
| Windows 机器 | 连大哥 | F1 Nuitka 真编译 |
| 域名 + 备案 | 连大哥 | F7 云部署 |
| EV 证书 | 连大哥 | F1 安装包签名 |
| 律师定稿 v3 | 连大哥找律师 | L1 协议正式签 |
| 个体工商户 | 连大哥 | 公司主体兜底 |
