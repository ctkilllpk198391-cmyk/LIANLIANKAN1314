# Phase 4 · 客户端产品化打包 · Requirements

> Spec ID：`phase4_packaging`
> 阶段：Phase 4（task_plan.md Week 4 Day 22-28）

---

## 1. 功能范围

让连大哥的**非技术朋友**能 3 click 装好白羊客户端并跑起来。

### 1.1 子模块
1. **Nuitka 打包**：Python → 单文件 .exe + 依赖 DLL
2. **代码签名**：EV 证书签 .exe（防杀毒报毒）
3. **安装引导 UX**：欢迎页 → 隐私说明 → 数据授权 → 完成
4. **自动更新**：客户端启动检查 → 后台下载 → 重启切新版
5. **崩溃上报**：Sentry self-hosted（不发第三方）
6. **远程配置热更**：UI 控件路径 JSON 静默拉

---

## 2. 验收

### 2.1 打包
- [ ] Nuitka 打包成功 · 单 .exe ≤ 80MB
- [ ] 双击 .exe 能跑（无 Python 依赖）
- [ ] 启动时间 < 5s
- [ ] 杀毒软件（Defender / 360 / 火绒）不误杀

### 2.2 安装
- [ ] 安装包 .exe 双击启动 · 3 步引导
- [ ] 用户协议 + 隐私政策必读 · 必勾选
- [ ] 微信账号授权弹窗（"允许白羊读取本机微信聊天记录用于训练你的专属分身？"）
- [ ] 安装到 `%LOCALAPPDATA%\Baiyang\` 不需要管理员

### 2.3 自动更新
- [ ] 启动时调 `GET https://baiyang.example/api/version` 比较
- [ ] 新版可用 → 后台下载 → 重启时切换
- [ ] 更新失败 → 回滚旧版

### 2.4 崩溃上报
- [ ] sentry-sdk 集成 · 客户端崩溃自动上报
- [ ] 上报数据脱敏（不含聊天内容）
- [ ] Sentry self-hosted 实例（不出腾讯云）

### 2.5 远程配置
- [ ] 微信 PC 升级后 control 路径变 → server 推 JSON
- [ ] 客户端 1 小时 poll 一次
- [ ] 配置加 sha256 校验防篡改

---

## 3. 边界

- ❌ 不做 macOS 客户端（连大哥客户全 Windows）
- ❌ 不做安装包多语言（中文 only）
- ❌ 不做 MSI 打包（直接 .exe + InnoSetup）
- ❌ 不做应用商店上架（直接私域分发）

---

## 4. 关键依赖

| 依赖 | 用途 |
|---|---|
| Nuitka | Python → exe |
| InnoSetup | 安装包向导 |
| EV Code Signing 证书 | 签名（年费 ¥3000-5000） |
| Sentry self-hosted | 崩溃上报 |
| sentry-python | SDK |
