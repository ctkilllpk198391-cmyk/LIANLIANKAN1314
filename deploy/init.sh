#!/usr/bin/env bash
# deploy/init.sh · 白羊生产环境一键初始化
# 用法: bash deploy/init.sh
# 前置: .env 文件已配置（参考 .env.example）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

echo "=========================================="
echo "  白羊 wechat_agent · 生产初始化"
echo "=========================================="

# ── 1. 检查 .env ─────────────────────────────────────────────────────────────
if [[ ! -f .env ]]; then
    echo "[ERROR] .env 不存在，请先复制 .env.example 并填写配置"
    exit 1
fi

source .env

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD 未设置}"
: "${BAIYANG_ADMIN_TOKEN:?BAIYANG_ADMIN_TOKEN 未设置}"

echo "[OK] .env 加载完成"

# ── 2. 拉取最新镜像 ───────────────────────────────────────────────────────────
echo "[INFO] 构建/拉取镜像..."
docker compose -f deploy/docker-compose.prod.yml pull postgres redis nginx --quiet
docker compose -f deploy/docker-compose.prod.yml build server

# ── 3. 启动基础服务 ───────────────────────────────────────────────────────────
echo "[INFO] 启动 postgres + redis..."
docker compose -f deploy/docker-compose.prod.yml up -d postgres redis

echo "[INFO] 等待 postgres 健康..."
until docker compose -f deploy/docker-compose.prod.yml exec -T postgres pg_isready -U baiyang; do
    sleep 2
done
echo "[OK] postgres 就绪"

# ── 4. 启动 server（init-db 在 lifespan 里自动执行） ─────────────────────────
echo "[INFO] 启动 server..."
docker compose -f deploy/docker-compose.prod.yml up -d server

echo "[INFO] 等待 server 健康..."
MAX_WAIT=60
ELAPSED=0
until curl -sf http://localhost:8327/v1/health > /dev/null 2>&1; do
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    if [[ $ELAPSED -ge $MAX_WAIT ]]; then
        echo "[ERROR] server 启动超时，检查日志: docker logs baiyang-server"
        exit 1
    fi
done
echo "[OK] server 就绪"

# ── 5. 创建初始管理员激活码（示例）────────────────────────────────────────────
echo "[INFO] 创建示例 flagship 激活码..."
CODE_RESP=$(curl -sf -X POST http://localhost:8327/admin/issue_code \
    -H "X-Admin-Token: ${BAIYANG_ADMIN_TOKEN}" \
    -H "Content-Type: application/json" \
    -d '{"plan":"flagship","valid_days":365}')
echo "[OK] 激活码: $(echo "$CODE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['code'])" 2>/dev/null || echo "$CODE_RESP")"

# ── 6. 启动 nginx ─────────────────────────────────────────────────────────────
echo "[INFO] 启动 nginx..."
docker compose -f deploy/docker-compose.prod.yml up -d nginx certbot
echo "[OK] nginx 已启动（HTTP 重定向生效，HTTPS 需先运行 deploy/certbot.sh）"

# ── 7. 汇报 ──────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  初始化完成！"
echo "  健康检查: curl http://localhost:8327/v1/health"
echo "  管理后台: http://<服务器IP>/admin?token=<BAIYANG_ADMIN_TOKEN>"
echo "  HTTPS 证书: bash deploy/certbot.sh <domain> <email>"
echo "=========================================="
