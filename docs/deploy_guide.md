# 白羊 wechat_agent · 云端部署手册

> 版本：v1.0 · 2026-04-16 · FDW F7

---

## 一、准备工作

### 1.1 域名注册

1. 阿里云万网注册域名（推荐 .com / .cn）
2. ICP 备案（中国大陆服务器必须）：
   - 准备材料：域名证书 + 服务器实例信息 + 法人身份证
   - 通过阿里云 ICP 代备案管理系统提交
   - 周期：约 20 工作日
   - 备案号加到网站底部（合规要求）
3. DNS 解析：在阿里云 DNS 控制台将域名 A 记录指向服务器公网 IP

### 1.2 服务器

| 规格 | 最低配置 | 推荐配置 |
|------|---------|---------|
| CPU | 2 核 | 4 核 |
| 内存 | 4 GB | 8 GB |
| 硬盘 | 40 GB SSD | 100 GB SSD |
| 带宽 | 3 Mbps | 10 Mbps |
| 系统 | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |

阿里云 ECS 开通步骤：
1. 控制台 → 云服务器 ECS → 创建实例
2. 选择区域（优先华东 / 华南，延迟低）
3. 选择实例规格（推荐 ecs.c7.xlarge 4c8g）
4. 系统盘 100G SSD
5. 安全组：开放 22（SSH）、80（HTTP）、443（HTTPS）
6. 设置 SSH 密钥对（禁止密码登录）

### 1.3 安装 Docker

```bash
# Ubuntu 22.04
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录后验证
docker --version
docker compose version
```

---

## 二、部署步骤

### 2.1 上传代码

```bash
# 方式 A：git clone（推荐）
git clone https://github.com/yourorg/wechat_agent.git /opt/wechat_agent
cd /opt/wechat_agent

# 方式 B：scp
scp -r ./wechat_agent root@<服务器IP>:/opt/wechat_agent
```

### 2.2 配置 .env

```bash
cd /opt/wechat_agent
cp .env.example .env
nano .env
```

必须设置：
```env
POSTGRES_PASSWORD=<随机强密码>
BAIYANG_ADMIN_TOKEN=<随机强 token>
BAIYANG_HERMES_MOCK=false
BAIYANG_ENV=production

# 可选 Sentry
SENTRY_DSN=
```

### 2.3 一键初始化

```bash
bash deploy/init.sh
```

脚本自动执行：
- 构建 server 镜像
- 启动 postgres + redis
- 启动 server（自动 init-db）
- 创建示例激活码
- 启动 nginx + certbot

### 2.4 配置 HTTPS

```bash
# 确保域名已解析到本机 IP，80 端口可访问
bash deploy/certbot.sh yourdomain.com admin@yourdomain.com
```

修改 nginx.conf 中的 `${DOMAIN}` 为真实域名后重载：
```bash
docker compose -f deploy/docker-compose.prod.yml exec nginx nginx -s reload
```

---

## 三、HTTPS 自动续期

certbot 容器已配置每 12h 自动检查并续期，无需手动操作。

验证续期状态：
```bash
docker logs baiyang-certbot
```

---

## 四、上线检查清单

### 服务健康
- [ ] `curl https://yourdomain.com/v1/health` 返回 `{"status":"ok"}`
- [ ] `curl http://yourdomain.com` 自动跳转 HTTPS（301）
- [ ] WebSocket 连接：`wscat -c wss://yourdomain.com/v1/ws/tenant_0001`

### 管理后台
- [ ] `https://yourdomain.com/admin?token=<ADMIN_TOKEN>` 可访问
- [ ] 客户列表正常加载
- [ ] 发激活码功能正常

### 安全
- [ ] SSH 只允许密钥登录（禁止密码）
- [ ] nginx admin location 已配置 IP 白名单（取消注释 allow/deny）
- [ ] .env 文件权限 600（`chmod 600 .env`）
- [ ] postgres / redis 不对外暴露端口（仅容器内网）

### 监控
- [ ] Sentry DSN 已配置且错误上报正常
- [ ] 设置告警（服务器 CPU > 80%、内存 > 85%）

---

## 五、日常运维

### 查看日志
```bash
docker logs -f baiyang-server
docker logs -f baiyang-nginx
```

### 重启服务
```bash
docker compose -f deploy/docker-compose.prod.yml restart server
```

### 更新部署
```bash
git pull
docker compose -f deploy/docker-compose.prod.yml build server
docker compose -f deploy/docker-compose.prod.yml up -d server
```

### 备份数据库
```bash
docker exec baiyang-postgres pg_dump -U baiyang baiyang > backup_$(date +%Y%m%d).sql
```

---

## 六、Sentry self-hosted（可选）

如需私有化 Sentry（不使用 sentry.io）：

```bash
docker compose -f deploy/sentry-compose.yml up -d
# 初始化（首次）
docker compose -f deploy/sentry-compose.yml run --rm sentry-web upgrade
# 访问 http://<服务器IP>:9000 完成向导
```

配置 DSN 后更新 .env：
```env
SENTRY_DSN=http://public_key@<服务器IP>:9000/1
```

详见 `docs/sentry_setup.md`。
