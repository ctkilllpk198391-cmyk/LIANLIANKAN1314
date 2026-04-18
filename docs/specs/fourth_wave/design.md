# Fourth Wave (FDW+) · Design

---

## 一、F2 激活码系统（核心）

```
[管理员] POST /admin/issue_code → 生成 ACTIVATION-CODE-XXXX-YYYY → 发给客户
[客户安装] setup.exe → 输码 → POST /v1/activate → 校验 + 绑设备 → 返 device_token
[客户端] 启动 → 用 device_token 拿数据 / 上传 / WS
[离线检测] 7 天没心跳 → 服务端禁用该 token · 客户重新激活
```

### Schema
```sql
CREATE TABLE activation_codes (
    code TEXT PRIMARY KEY,           -- "WXA-2026-A1B2-C3D4-E5F6"
    plan TEXT NOT NULL,              -- trial/pro/flagship
    valid_days INTEGER NOT NULL,     -- 30/365
    issued_at INTEGER NOT NULL,
    activated_at INTEGER,            -- 激活时间 · null=未激活
    activated_tenant_id TEXT,        -- 激活后绑定 tenant
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE device_bindings (
    device_token TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    activation_code TEXT NOT NULL,
    machine_guid TEXT NOT NULL,      -- Windows Machine GUID
    bound_at INTEGER NOT NULL,
    last_heartbeat_at INTEGER NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
```

### server/activation.py
```python
class ActivationService:
    def generate_code(plan, valid_days=365) -> str
    async def activate(code, machine_guid) -> str  # 返 device_token
    async def revoke_code(code)
    async def heartbeat(device_token)              # 客户端 30 分钟一次
    async def is_valid(device_token) -> bool        # API 鉴权用
```

---

## 二、F1 + F3 + F4 客户端打包

### installer/nuitka_build.py
```bash
nuitka --standalone --windows-disable-console \
       --enable-plugin=pyqt6 \
       --include-package=client,server \
       --output-dir=dist \
       client/main.py
```

### installer/setup.iss（InnoSetup）
- 协议页（强制阅读 user_agreement_v3.md）
- 输激活码字段
- 创建桌面快捷方式 + 开机自启（注册表 HKCU\...\Run）

### client/updater.py
```python
class Updater:
    async def check(self) -> Optional[UpdateInfo]:
        """启动时调 server /v1/version · 比当前版本新 → 静默下载到 temp"""
    async def apply_on_next_boot(self):
        """下次启动用 batch script 替换 exe"""
```

### client/tray.py
```python
import pystray
def build_tray(on_pause, on_resume, on_quit) -> pystray.Icon:
    """绿/黄/红 3 色图标 + 菜单"""
```

---

## 三、F5 + F6 鉴权 + 管理后台

### server/auth.py
```python
@dataclass
class AuthContext:
    tenant_id: str
    device_token: str
    plan: str

class AuthMiddleware:
    async def authenticate(authorization_header: str) -> Optional[AuthContext]
        # Bearer <device_token> → 查 device_bindings → 返 AuthContext
```

集成：FastAPI dependency `Depends(auth_required)` 加到 dashboard / control / accounts 等敏感路由。

### server/admin.py
- ADMIN_TOKEN env 静态校验（简单）· prod 升 OAuth
- GET /admin/customers · 所有 tenant 列表 + health + plan + revenue
- POST /admin/issue_code · 生成激活码（plan + valid_days）
- GET /admin/health/{tenant} · 单客户深度诊断
- POST /admin/revoke/{code} · 撤销激活码

---

## 四、F7 + F8 云部署

### deploy/docker-compose.prod.yml
```yaml
services:
  server:
    build: .
    environment:
      BAIYANG_DB_URL: postgresql+asyncpg://...
      BAIYANG_HERMES_MOCK: "false"
      ...
    depends_on: [postgres, redis]
  postgres:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
  nginx:
    image: nginx:alpine
    ports: ["80:80", "443:443"]
    volumes: [./nginx.conf:/etc/nginx/nginx.conf, ./certs:/etc/letsencrypt]
```

### deploy/nginx.conf
- HTTPS 终止
- /v1/* → server:8327
- /v1/ws/* → server:8327 (WebSocket upgrade)
- /admin → server:8327 (加 IP whitelist)

### deploy/sentry-compose.yml（独立 stack）
- sentry-self-hosted 简化版
- 客户端集成 sentry-sdk · DSN 走环境变量

---

## 五、L1-L5 法律防护

### L1 协议 v3
- legal/user_agreement_v3.md（律师友好 · 中文）
- 包含：服务范围 · 资费 · 数据归属（链接 data_ownership.md）· **微信合规免责** · **灰产拒绝列表** · 责任限制 · 争议解决

### L2 灰产拒绝（compliance_check.py）
```python
GRAY_KEYWORDS = {
    "gambling": ["博彩", "赌", "下注", "百家乐", "彩票"],
    "porn": ["色情", "成人", "AV", "约炮"],
    "fraud": ["诈骗", "钓鱼", "假冒", "传销", "MLM"],
    "medical": ["确诊", "药方", "处方", "治愈"],   # 医诊
    "finance": ["保证收益", "稳赚", "荐股", "炒股", "投资群"],
}

def detect_gray_intent(text: str) -> Optional[str]:
    """返回命中类别 or None"""
```

集成：generator.generate 第一步检测客户文本 · 命中 → 拒绝生成 · 转人工 · audit "compliance_blocked"
knowledge_base.ingest 检测上传内容 · 命中 → 拒绝入库 + 警告

### L3 举报检测（client/wechat_alert_detector.py）
- wxauto 监听窗口 title / dialog text
- 关键词："被举报" "违规" "限制" "封禁" "异常"
- 命中 → 立即调 server `/v1/control/{tenant}/emergency_stop` → notifier 紧急推老板

### L4 举证日志
- audit_log 加 `legal_evidence_payload` JSON 字段：
```json
{
  "consent_version": "v3.2026-04-16",
  "consent_signed_at": 1234567890,
  "auto_send_enabled": true,
  "auto_send_enabled_at": 1234567890,
  "client_ip": "1.2.3.4",
  "machine_guid": "..."
}
```
- server/legal_export.py 一键导出律师举证包

### L5 行业合规分级
- TenantConfig 加 `industry_compliance_level`（normal / sensitive / restricted）
- sensitive 行业（医美/教培/金融）：
  - 默认 high_risk_block=True
  - 启动时弹专属"医美合规承诺"/"金融非荐股声明"
- restricted（赌/色/诈骗）：
  - 启动时检测 → 拒绝服务 + 上报 admin

---

## 六、依赖图（执行顺序）

```
独立批次（强并行）：
├── L1-L5 法律防护         ← 我做（涉及多模块 · 必须我连贯做）
├── F2+F5 激活码+Web鉴权    ← 派 sonnet（关联）
├── F1+F3+F4 客户端打包     ← 派 sonnet（client/* + installer/*）
└── F6+F7+F8 后台+部署+Sentry ← 派 sonnet（admin + deploy/*）

集成（最后 1 天）：
└── main.py 集成 L 系列 + e2e 5 场景 + 文档 v7
```

---

## 七、测试策略

### 单测（≥50）
- F1: test_installer_config.py（≥3）
- F2: test_activation.py（≥10）
- F3: test_updater.py（≥4）
- F4: test_tray.py（≥3 mock）
- F5: test_auth.py（≥6）
- F6: test_admin.py（≥6）
- L1-L5: test_compliance_check.py + test_wechat_alert_detector.py + test_legal_export.py + test_industry_compliance.py（≥18）

### e2e 5 场景
1. 激活码：发码 → 客户激活 → device_token 工作
2. Web 登录：输码 → 拿 token → 看 dashboard
3. 自动更新：客户端 v1 启动 → 检测 v2 → 静默更新
4. 灰产拒绝：客户问"能赌博吗" → AI 拒绝 + audit
5. 举报检测：mock wxauto 触发"被举报" → emergency_stop + notify
