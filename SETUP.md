# 白羊 · 完整环境配置指南

> 双端配置：服务端（macOS/Linux/Windows）+ 客户端（仅 Windows）

---

## 一、服务端（macOS · 推荐 Phase 1 用）

### 1.1 前置

| 工具 | 版本 | 安装方式 |
|---|---|---|
| Python | ≥ 3.11 | `brew install python@3.11` |
| uv | latest | `brew install uv` |
| SQLite | 3.x | macOS 自带 |
| (可选) PostgreSQL 16 | Phase 2 | `brew install postgresql@16` |

### 1.2 安装

```bash
cd ~/wechat_agent

# 创建 venv + 装依赖
make install

# 验证
.venv/bin/python -c "import server.main; print('✅ server import OK')"
```

### 1.3 配置

```bash
cp config/config.example.yaml config/config.yaml
cp config/tenants.example.yaml config/tenants.yaml
cp .env.example .env

# 编辑 .env 填实际值（DB_URL / HERMES_URL / classifier_mode）
```

### 1.4 数据库

```bash
make init-db    # 创建 SQLite + schema
make seed       # 种子 tenant_0001（连大哥）
```

### 1.5 启动

```bash
make run        # 后台跑：BAIYANG_HERMES_MOCK=true uvicorn server.main:app --port 8327
```

### 1.6 验证

```bash
curl http://127.0.0.1:8327/v1/health
# {"status":"ok","version":"0.1.0","hermes_reachable":true,"db_reachable":true,"tenants_loaded":1}

curl -X POST http://127.0.0.1:8327/v1/inbound \
  -H 'Content-Type: application/json' \
  -d '{"tenant_id":"tenant_0001","chat_id":"test","sender_id":"测试","sender_name":"测试","text":"在么","timestamp":1713200000}'
```

---

## 二、客户端（Windows · Phase 1 仅在 Windows 上真跑）

### 2.1 前置

| 工具 | 版本 | 安装 |
|---|---|---|
| Windows | 10/11 | — |
| Python | 3.11 | https://python.org |
| 微信 PC | 4.0.x / 4.1.x | https://weixin.qq.com |
| Git | latest | https://git-scm.com |

### 2.2 安装

```powershell
cd C:\wechat_agent

# venv
python -m venv .venv
.\.venv\Scripts\activate

# 装基础 + windows 套件
pip install -e ".[windows]"
```

### 2.3 微信 PC 准备

1. 安装微信 4.0.x 或 4.1.x（确认非 3.9）
2. 登录微信账号
3. **关闭"自动登录"选项**（首次需要扫码）
4. 微信窗口必须始终保持可见（不能最小化）

### 2.4 客户端配置

```powershell
copy config\client.example.yaml config\client.yaml
notepad config\client.yaml
# 填 server_url=http://你的服务器IP:8327
```

### 2.5 跑客户端

```powershell
python -m client.main --tenant tenant_0001
# 启动后保持微信窗口前置即可
```

---

## 三、macOS 上跑 client mock 模式（开发用）

```bash
cd ~/wechat_agent
make install

# mock 模式 client（不实际监听微信，用于跑通逻辑）
.venv/bin/python -c "
import asyncio
from client.watcher import WeChatWatcher
async def main():
    w = WeChatWatcher('http://127.0.0.1:8327', 'tenant_0001', mock=True)
    await w.start()
asyncio.run(main())
"
```

---

## 四、PostgreSQL 升级（Phase 2）

```bash
brew install postgresql@16
brew services start postgresql@16

createdb hermes_baiyang
psql hermes_baiyang -c "CREATE EXTENSION vector;"

# 改 .env
echo 'BAIYANG_DB_URL=postgresql+asyncpg://localhost/hermes_baiyang' >> .env

# 重建 schema
make init-db
```

---

## 五、常见问题

### Q1: macOS 上 wxautox 装不上
A: 正常。wxautox 是 Windows-only。Phase 1 用 mock=True 跑通逻辑即可，真测等 Windows。

### Q2: PostgreSQL 没装能跑吗
A: 能。Phase 1 用 SQLite（默认）。Phase 2 训 LoRA 时再上 PostgreSQL。

### Q3: hermes-agent 没启动
A: 没关系。`.env` 设 `BAIYANG_HERMES_MOCK=true` 用 mock 响应。

### Q4: 端口 8327 被占用
A: 改 `.env` 的 `BAIYANG_PORT=xxxx` 或在 Makefile 改 `make run`。

### Q5: pytest 报 "ModuleNotFoundError"
A: 确认在 venv 内：`source .venv/bin/activate`。或用 `make test`。

---

## 六、Phase 进展指引

| Phase | 你需要做的 | 等多久 |
|---|---|---|
| Phase 1 | macOS server 跑通 + 测试全绿 | 已就绪 |
| Phase 2 | Windows 微信 + WeChatMsg 导出 + LoRA 训练 | 等连大哥 |
| Phase 3 | vLLM 部署 + 多 LoRA + Qt6 浮窗 | 等连大哥 |
| Phase 4 | Nuitka 打包 + 自动更新 | 等连大哥 |
| Phase 5 | 微信支付 + 5 个种子客户 | 等连大哥 |
| Phase 6 | 第一个付费客户（PMF）| 等连大哥 |
| Phase 7-8 | 1 → 10 付费客户 | 等连大哥 |
