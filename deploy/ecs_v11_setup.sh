#!/bin/bash
# V11 ECS 部署脚本 — 一键真跑通 WeChatPadPro + chisel server + wechat_agent server
# 用法: 启 GPU 实例 → SSH 进 → bash ecs_v11_setup.sh

set -e

echo "=== V11 ECS 部署开始 $(date) ==="

# 1. 装 Docker (Ubuntu 22.04)
if ! command -v docker &> /dev/null; then
    echo "装 Docker..."
    curl -fsSL https://get.docker.com | bash
    apt-get install -y docker-compose-plugin
fi

# 2. 装 chisel server (反向 SOCKS5 通道入口)
if ! command -v chisel &> /dev/null; then
    echo "装 chisel..."
    CHISEL_VER="1.10.1"
    wget -q "https://github.com/jpillora/chisel/releases/download/v${CHISEL_VER}/chisel_${CHISEL_VER}_linux_amd64.gz"
    gunzip "chisel_${CHISEL_VER}_linux_amd64.gz"
    chmod +x "chisel_${CHISEL_VER}_linux_amd64"
    mv "chisel_${CHISEL_VER}_linux_amd64" /usr/local/bin/chisel
fi

# 3. 启 chisel server (后台 systemd)
cat > /etc/systemd/system/chisel.service <<'EOF'
[Unit]
Description=Chisel Server (reverse SOCKS5 for WeChatPadPro)
After=network.target

[Service]
ExecStart=/usr/local/bin/chisel server --port 7000 --auth wechat:agent2026 --reverse
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable chisel
systemctl restart chisel
echo "✅ chisel server 启动: 0.0.0.0:7000"

# 4. 部 WeChatPadPro Docker
mkdir -p /opt/wechat_agent && cd /opt/wechat_agent
if [ ! -d "WeChatPadPro" ]; then
    git clone https://github.com/WeChatPadPro/WeChatPadPro.git
fi
cd WeChatPadPro/deploy

# 改 docker-compose.yml 配 SOCKS5 出口走 chisel (host 上的 :1080)
cat > .env <<EOF
MYSQL_ROOT_PASSWORD=$(openssl rand -hex 16)
MYSQL_DATABASE=weixin
MYSQL_USER=weixin
MYSQL_PASSWORD=$(openssl rand -hex 16)
MYSQL_PORT=3306
REDIS_PASSWORD=$(openssl rand -hex 16)
REDIS_PORT=6379
WECHAT_PORT=8080
DB_HOST=wechatpadpro_mysql
DB_PORT=3306
DB_DATABASE=weixin
DB_USERNAME=weixin
DB_PASSWORD=\${MYSQL_PASSWORD}
REDIS_HOST=wechatpadpro_redis
REDIS_DB=0
ADMIN_KEY=$(openssl rand -hex 32)
HTTP_PROXY=socks5://host.docker.internal:1080
HTTPS_PROXY=socks5://host.docker.internal:1080
EOF

docker compose up -d
echo "✅ WeChatPadPro Docker 启动: localhost:8080"

# 5. 装 wechat_agent server (clone repo, 启 FastAPI)
cd /opt/wechat_agent
if [ ! -d "repo" ]; then
    git clone https://github.com/ctkilllpk198391-cmyk/LIANLIANKAN1314.git repo
fi
cd repo
pip3 install -r requirements.txt
nohup python3 -m server.main > /var/log/wechat_agent_server.log 2>&1 &
echo "✅ wechat_agent server 启动: 0.0.0.0:8327"

# 6. 配防火墙 (开 7000 chisel + 8327 server, 不开 8080 WeChatPadPro 内部)
ufw allow 7000/tcp
ufw allow 8327/tcp

# 7. 输出关键信息
echo ""
echo "============================================================"
echo "V11 部署完成"
echo "  chisel server:        $(curl -s ifconfig.me):7000 (auth: wechat:agent2026)"
echo "  WeChatPadPro:         http://127.0.0.1:8080 (内部)"
echo "  wechat_agent server:  http://$(curl -s ifconfig.me):8327"
echo "  ADMIN_KEY: $(grep ADMIN_KEY /opt/wechat_agent/WeChatPadPro/deploy/.env | cut -d= -f2)"
echo "============================================================"
