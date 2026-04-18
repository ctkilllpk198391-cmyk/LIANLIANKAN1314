# Sentry 集成指南 · wechat_agent

> FDW F8 · 2026-04-16

---

## 一、DSN 申请

### 方式 A：使用 sentry.io（推荐快速验证）

1. 访问 https://sentry.io → 注册 / 登录
2. 创建新 Project → Platform 选 **Python**
3. 复制 DSN（格式：`https://xxx@oXXX.ingest.sentry.io/YYYY`）

### 方式 B：self-hosted Sentry

```bash
# 启动
docker compose -f deploy/sentry-compose.yml up -d

# 首次初始化（创建管理员账号）
docker compose -f deploy/sentry-compose.yml run --rm sentry-web upgrade

# 访问 http://<服务器IP>:9000
# Organization → Project → DSN
```

---

## 二、环境变量配置

在服务器 `.env` 文件添加：

```env
# Sentry DSN（客户端和服务端共用或分开）
SENTRY_DSN=https://xxx@oXXX.ingest.sentry.io/YYYY

# 环境标识（production / staging / dev）
BAIYANG_ENV=production

# 采样率（0.0-1.0，建议生产 0.1）
SENTRY_TRACES_SAMPLE_RATE=0.1
```

---

## 三、服务端集成

`server/sentry_init.py` 已实现，在 FastAPI lifespan 启动时自动初始化。

功能：
- 自动捕获未处理异常
- SQLAlchemy 慢查询追踪
- FastAPI 请求 tracing
- `before_send` 过滤 request body（防止客户聊天内容泄露）

验证：
```bash
# 触发测试错误
curl -X POST http://localhost:8327/v1/inbound \
  -H "Content-Type: application/json" \
  -d '{"intentionally_invalid": true}'

# 查看 Sentry 是否收到错误
```

---

## 四、客户端集成

`client/sentry_init.py` 已实现，在 `client/main.py` 启动时调用：

```python
from client.sentry_init import init_sentry, set_user
from shared.const import VERSION

init_sentry(release=VERSION)
set_user(tenant_id)   # 激活后设置
```

功能：
- 崩溃捕获（未处理异常）
- `capture_exception()` 手动上报
- `before_send` 过滤 request 字段

---

## 五、隐私说明

Sentry 上报内容严格过滤：
- 不含客户聊天原文（`before_send` 移除 request.data）
- 不含 session cookies
- 仅含 tenant_id 标签（便于排查）
- 服务端仅上报异常堆栈 + 系统信息

---

## 六、告警配置（sentry.io）

推荐配置以下告警规则：

| 规则 | 阈值 | 通知 |
|------|------|------|
| 新错误 | 首次出现 | 企业微信 / 邮件 |
| 错误率 | > 10/min | 紧急通知 |
| P50 响应时间 | > 2s | 邮件 |

---

## 七、sentry-sdk 安装

```bash
pip install sentry-sdk[fastapi]
# 或仅基础版
pip install sentry-sdk
```

pyproject.toml 中添加（可选依赖）：
```toml
[project.optional-dependencies]
sentry = ["sentry-sdk[fastapi]>=1.40"]
```
