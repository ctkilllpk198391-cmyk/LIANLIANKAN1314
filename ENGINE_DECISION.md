# wechat_agent 引擎决策 (2026-05-03)

> V2-V10 wxauto4 路线全部失败, 真转 iPad 协议 WeChatPadPro 双层架构.

## V2-V10 死亡复盘

| 版本 | 真挂在 |
|------|--------|
| V2-V6 | spec exclude 'tkinter', wxauto4 ImportError |
| V7 | tkinter 修了, wxauto4 抛 "未找到主窗口" |
| V8 | 误诊 "客户没开微信" (用户怒喊 "我开了!") |
| V9 | 给精准诊断 + 微信 4.0.5.26 下载链接 |
| V10 | 一体安装包内嵌微信 4.0.5.26, 但 4.0.5 老版**登录受限** |

**真根因**: wxauto4 v41.1.2 hardcoded ClassName **只支持微信 4.0.5.13/4.0.5.26**, 且 4.0.5 老版微信腾讯已限制登录 (k2y1982/wutongai 真反馈).

**真证据**: cluic/wxauto4 issue #7 maintainer 真回 "若要使用 wxauto4，请使用 4.0.5.13 或者 4.0.5.26 版本的微信" + "开源版后续不再维护".

## 真新方向: WeChatPadPro iPad 协议

### 真证据 (tavily 真搜 2026-05-03)

| 维度 | 状态 |
|------|------|
| ⭐2385 真活 v868/v2.01 | ✅ |
| iOS 18.7 协议最新 | ✅ |
| Linux binary 22MB (linux-amd64/arm64/mips64) | ✅ |
| **无 Windows binary** | ⚠️ 必 ECS Linux 部署 |
| Docker 真免费 (赞助可选) | ✅ |
| 1400+ Telegram 用户群 + 风控指南 | ✅ |
| 用户实证 (lian 24h 不封 + dify-on-wechat 群) | ✅ |

### 真风险 (issue #67 真案例)

1. 新号扫码后 **1 周内被群拉直接封号** — 维护者真说 "養號先"
2. 多账号同设备 IP → 风控
3. 高频/重复/24h 无间断 → 封号
4. 被举报 → 封号高概率

## 真架构: 双层 — 客户 IP 出口防风控 ⭐ 核心

```
[客户机 wechat_agent.exe ~5MB]
   ├── 轻量 SOCKS5 server (走客户家用 IP)
   └── 显示扫码 UI (登录用)
        ↕ (经客户 IP 出口)
[阿里云 ECS]
   ├── WeChatPadPro Docker (linux-amd64, 22MB)
   │   └── 配置走客户机 SOCKS5 → 走客户家用 IP 登录微信
   ├── wechat_agent server (LLM 生成回复, 已有)
   └── MySQL + Redis (会话状态)
```

**关键**: 微信流量必须经客户家用 IP 出口, 不能用阿里云 IP (云 IP 真触发风控).

**Why**:
- 阿里云固定 IP → 微信风控判 "登录环境异常" 直接封
- 客户家用 IP 真匹配客户日常微信使用 → 风控通过
- 客户机做 SOCKS5 出口 → 微信看到的是客户家用 IP

**Trade-off**:
- ✅ 防风控 (核心目标)
- ⚠️ 客户关机 = SOCKS5 断 = 服务暂停, 客户开机自动恢复
- ⚠️ 客户机要 7x24 开 (或工作时段开)

## 真客户体验

```
客户操作:
1. 装 wechat_agent.exe (5MB, 轻量, 无微信打扰)
2. 看桌面弹窗扫码 (5 秒)
3. 完成 (后续全自动 24h)
```

**对比 V10**: V10 装 250MB + 替换微信 + 登录 4.0.5 受限. **V11 是真"装即用"**.

## Plan B 多引擎抽象层 (待实施)

```python
# server/engine_adapter.py
class WeChatEngine(ABC):
    def send_message(self, chat, text): ...
    def receive_messages(self): ...

# 实现:
# WeChatPadProEngine — Plan A (iPad 协议, 默认)
# WxautoEngine      — Plan B (UI 自动化 + 微信 3.9.12, 不同打击面)
# OCRMouseEngine    — Plan C (终极, 任何版本)
```

任一被打 → 配置切换 → 客户无感 30s 切换.

**用户决: 先做 Plan A 单引擎, 跑稳后再叠加 Plan B/C.**

## 真未实施清单 (V11 路线)

- [ ] 阿里云 ECS 部署 WeChatPadPro Docker (linux-amd64 22MB)
- [ ] 客户机 wechat_agent.exe 改为 SOCKS5 server + 扫码 UI (5MB)
- [ ] WeChatPadPro 配置走客户 SOCKS5 出口
- [ ] server 集成 WeChatPadPro REST API (替代 wxauto4 整套)
- [ ] 客户养号 SOP 文档 (1 周不加群 / 慢速 / 不重复内容)

## 真链接

- WeChatPadPro: https://github.com/WeChatPadPro/WeChatPadPro
- v2.01 release: https://github.com/WeChatPadPro/WeChatPadPro/releases/tag/v2.01
- 在线 demo: https://wx.knowhub.cloud/ (默认密钥 28d21d0f9748172c970ba4c208af5564)
- Telegram 群: https://t.me/+LK0JuqLxjmk0ZjRh
- issue #67 风控真案例: https://github.com/WeChatPadPro/WeChatPadPro/issues/67
- cluic/wxauto4 issue #7 (wxauto4 死路真证): https://github.com/cluic/wxauto4/issues/7
