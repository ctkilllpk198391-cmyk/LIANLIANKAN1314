#!/usr/bin/env bash
# deploy/certbot.sh · Let's Encrypt 初次签发 + 自动续期
# 用法: bash deploy/certbot.sh <domain> <email>
# 示例: bash deploy/certbot.sh baiyang.example.com admin@example.com

set -euo pipefail

DOMAIN="${1:?Usage: $0 <domain> <email>}"
EMAIL="${2:?Usage: $0 <domain> <email>}"
WEBROOT="/var/www/certbot"

echo "==> 签发证书: ${DOMAIN} (${EMAIL})"

# 确保 nginx 已启动（webroot 模式需要 80 端口可访问）
if ! docker compose -f "$(dirname "$0")/docker-compose.prod.yml" ps nginx | grep -q "running"; then
    echo "[WARN] nginx 未运行，请先 docker compose up -d nginx"
fi

docker run --rm \
    -v certbot-conf:/etc/letsencrypt \
    -v certbot-www:/var/www/certbot \
    certbot/certbot:latest certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${EMAIL}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}"

echo "==> 证书签发完成，证书位于 /etc/letsencrypt/live/${DOMAIN}/"
echo "==> 配置 nginx.conf 中的 \${DOMAIN} 为 ${DOMAIN} 后重载 nginx"
echo "==> 自动续期由 certbot 容器每 12h 检查一次，无需额外操作"
