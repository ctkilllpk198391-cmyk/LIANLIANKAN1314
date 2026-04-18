# WechatAgent 客户安装指南

> 适用于:微信 PC 4.0+ · Windows 10/11
> 安装时间:1-2 分钟

---

## 三步装好

### Step 1 · 下载安装包

浏览器打开:
```
http://120.26.208.212/download/WechatAgent-Setup.exe
```

下载到桌面或下载文件夹(约 60 MB)。

### Step 2 · 双击运行 setup.exe

会弹出安装向导:

1. **同意用户协议** → Next
2. **激活码页**:输入您的激活码 `WXA-XXXX-XXXX-XXXX-XXXX`
3. **服务器配置页**:保持默认(已经填好)→ Next
4. **安装目录**:默认 `C:\Users\<你>\AppData\Local\WechatAgent`(无需管理员权限)→ Next
5. **附加任务**:✅ 创建桌面快捷方式 ✅ 开机自启 → Next
6. **Install** → 等 30 秒
7. ✅ 启动 WechatAgent → Finish

### Step 3 · 登录微信 PC

确保微信 PC 已经登录(看任务栏有微信图标)。

WechatAgent 会自动:
- 监听微信新消息
- 通过 AI 自动生成回复
- 模拟人手发送(节奏拟人 · 反封号)

---

## 验证装好了

### A · 看托盘
任务栏右下角应该有 WechatAgent 黑色 cmd 窗口(后续会改成系统托盘图标)

### B · 测试 AI 回复
1. 用**手机微信**给**自己 PC 微信**发一条:`你好 玉兰油精华多少钱`
2. 3 秒内 PC 微信应该自动回复

### C · 看服务器 Dashboard
浏览器打开:
```
http://120.26.208.212/admin
```

看 audit 记录里有这条对话。

---

## 卸载

开始菜单 → WechatAgent → 卸载 WechatAgent

或者控制面板 → 程序 → 找 WechatAgent → 卸载。

---

## 常见问题

### Q · 微信没登录,客户端会怎样?
A · 客户端会等 5 秒后退出。重新登录微信后,双击桌面 WechatAgent 快捷方式重启即可。

### Q · 想暂停 AI 自动回?
A · 任务管理器关掉 wechat_agent.exe 进程。下次开机会自启,要永久关:开始菜单搜 `启动` → 取消 WechatAgent 勾选。

### Q · 想换激活码?
A · 卸载重装。或者改 `C:\Users\<你>\AppData\Local\WechatAgent\.env` 里的 `BAIYANG_ACTIVATION_CODE=`。

### Q · 服务器换地址了?
A · 同上改 `.env` 里的 `BAIYANG_SERVER_URL=`。

---

## 出问题怎么办

1. 任务栏右下角找 WechatAgent 黑色 cmd 窗口,前置截图
2. 截图发给客服
3. 或者去 `C:\Users\<你>\AppData\Local\WechatAgent\` 看是否有 logs/ 目录,把里面文件压缩发客服

---

**提示**:这是 v0.1 早期版本,后续会升级:
- 系统托盘图标(代替黑色 cmd 窗口)
- 一键暂停/恢复按钮
- 内置 dashboard
- 自动更新
