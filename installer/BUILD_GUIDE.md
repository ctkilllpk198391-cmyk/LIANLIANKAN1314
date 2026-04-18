# WechatAgent 安装包构建指南 · 连大哥版

> 目标:GitHub Actions 自动编译 → 出 `WechatAgent-Setup.exe` → 上传服务器 → 客户下载双击装
> 一次配好,以后每次改代码都能自动出新版本

---

## 你做的(一次性 · 10 分钟)

### Step 1 · 创建 GitHub 账号(已有跳过)

访问 https://github.com/signup
- 邮箱:用你常用的
- 用户名:随便取(英文 · 别人不太能搜到也行)
- 免费版即可

### Step 2 · 创建 wechat_agent 仓库

1. 登录后点右上角 `+` → `New repository`
2. Repository name:`wechat_agent`
3. **Private**(私有 · 别让人看到代码)
4. 不要勾任何 Initialize 选项(README/gitignore/license 都不勾)
5. 点 `Create repository`

### Step 3 · 把代码推到 GitHub

复制创建后页面里的命令,大概长这样(把 `YOUR-USERNAME` 换成你的):

```bash
cd /Users/lian/wechat_agent
git init
git add -A
git commit -m "initial commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/wechat_agent.git
git push -u origin main
```

第一次 push 可能要登录。GitHub 现在不接受密码,要用 **Personal Access Token (PAT)**:
- GitHub 右上角头像 → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token
- 勾 `repo` 权限
- Copy 那个 `ghp_xxxxx` token
- push 时 username 用 GitHub 用户名,password 粘贴这个 token

**或者** — 告诉我你的 GitHub 用户名 + token,我帮你 push(更省事)。

### Step 4 · 触发 Windows 编译

push 完成后:
1. 浏览器打开你的 repo `https://github.com/YOUR-USERNAME/wechat_agent`
2. 点顶部 `Actions` 标签
3. 左边 workflows 列表点 `Build Windows Setup`
4. 右上角 `Run workflow` 按钮 → `Run workflow`
5. 等约 10-15 分钟(免费 windows-latest runner 编译)

### Step 5 · 下载 setup.exe

编译完成后:
1. 点这次 workflow run 详情
2. 拉到底部 `Artifacts` 区域
3. 点 `WechatAgent-Setup` 下载(zip 包)
4. 解压得到 `WechatAgent-Setup.exe`

---

## 我做的(自动 · 你不用管)

- ✅ 写 PyInstaller spec(`installer/wechat_agent.spec`):打包成单 exe 含 Python runtime
- ✅ 写 Inno Setup 配置(`installer/setup.iss`):带激活码 wizard + 桌面/开机自启 + 用户级安装(无需 admin)
- ✅ 写 GitHub Actions workflow(`.github/workflows/build-windows.yml`):windows-latest 自动编译
- ✅ 拿到 setup.exe 后我上传服务器 `http://120.26.208.212/download/WechatAgent-Setup.exe`

---

## 客户操作(以后所有客户都这一套)

1. 浏览器打开 `http://120.26.208.212/download/WechatAgent-Setup.exe` → 自动下载
2. 双击 setup.exe
3. 弹安装向导:
   - 同意协议
   - 输入激活码 `WXA-XXXX-XXXX-XXXX-XXXX`
   - 服务器/Tenant 默认填好(高级才改)
   - 选择安装目录(默认 `%LocalAppData%\WechatAgent` · 无需 admin)
   - 勾选 `桌面快捷方式` + `开机自启`
4. 点完成 → 自动启动客户端
5. 客户登录微信 PC 版即可

---

## 改代码后重新出包(以后)

每次你改了代码:
```bash
cd /Users/lian/wechat_agent
git add -A
git commit -m "feat: 改了什么"
git push
```

然后到 GitHub Actions 点一下 `Run workflow`,15 分钟出新 setup.exe。

打 tag 自动 release:
```bash
git tag v0.2.0
git push --tags
```
会自动出 GitHub Release 含 setup.exe 下载链接。

---

## 一句话

**你给我 GitHub 用户名 + 帮我创建 repo,剩下的我全干。**

或者你直接发我 GitHub username + Personal Access Token,我帮你 git push + 触发 build,你只需要等 15 分钟下载 setup.exe。
