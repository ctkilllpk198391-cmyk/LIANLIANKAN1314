# Fourth Wave (FDW+) · Tasks

> feature_id: `fourth_wave`
> 完成标准：所有 [x] + e2e 5 场景过 + pytest ≥519 全绿

---

## 批次 A · Day 0-3 · 4 路并行

### A1 · L1-L5 法律防护（我做）
- [ ] legal/user_agreement_v3.md 强化协议
- [ ] server/compliance_check.py 灰产关键词检测
- [ ] generator 集成 compliance（生成前拒绝）
- [ ] knowledge_base.ingest 灰产内容拒绝
- [ ] client/wechat_alert_detector.py 举报检测
- [ ] server emergency_stop 路由
- [ ] audit_log 加 legal_evidence_payload
- [ ] server/legal_export.py 律师举证导出
- [ ] TenantConfig 加 industry_compliance_level
- [ ] sensitive/restricted 启动校验
- [ ] tests ≥22 用例

### A2 · F2+F5 激活码+鉴权（subagent sonnet）
- [ ] schema + models.py 加 activation_codes + device_bindings
- [ ] server/activation.py
- [ ] client/activation.py
- [ ] server/auth.py middleware
- [ ] dashboard 加 Bearer token
- [ ] HTML 加登录页
- [ ] 路由 /v1/activate /v1/activation/* + dashboard 加鉴权
- [ ] tests ≥16

### A3 · F1+F3+F4 客户端打包（subagent sonnet）
- [ ] installer/nuitka_build.py
- [ ] installer/setup.iss
- [ ] installer/build.sh
- [ ] client/updater.py
- [ ] server/version_api.py
- [ ] client/tray.py（pystray）
- [ ] tests ≥10

### A4 · F6+F7+F8 后台+部署+Sentry（subagent sonnet）
- [ ] server/admin.py + auth
- [ ] templates/admin.html
- [ ] deploy/docker-compose.prod.yml
- [ ] deploy/nginx.conf
- [ ] deploy/certbot.sh
- [ ] deploy/init.sh
- [ ] docs/deploy_guide.md
- [ ] deploy/sentry-compose.yml
- [ ] client/sentry_init.py + server/sentry_init.py
- [ ] docs/sentry_setup.md
- [ ] tests ≥6

---

## 批次 B · Day 7-9 · 集成 + 收尾

### B1 · main.py 集成
- [ ] App 加 activation / auth / admin / compliance
- [ ] inbound 集成 compliance_check（最前置）
- [ ] knowledge_ingest 集成 compliance
- [ ] 启动时校验 tenant consent v3
- [ ] pytest >=519 全绿

### B2 · e2e 5 场景
- [ ] tests/e2e/test_fourth_wave_e2e.py
- [ ] 激活码 / Web 登录 / 自动更新 / 灰产拒绝 / 举报检测

### B3 · 文档 v7（subagent sonnet）
- [ ] STATUS_HANDOFF v7（FDW+ 完成 · 上线 ready）
- [ ] progress 加 Session 6
- [ ] task_plan 标 FDW+ 完成 · 标 上线 ready
- [ ] findings 加 § 14 法律风险评估 + 规避策略
- [ ] README 加 FDW + 部署指南链接

### B4 · 启动验收
- [ ] uvicorn 启动 + curl 新路由 + admin 后台
- [ ] grep TODO/FIXME = 0
- [ ] aivectormemory 记忆 3 条（FDW+ 完成 / 激活码设计 / 法律防护策略）
