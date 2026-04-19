#!/bin/bash
# Wave 13 · 6 环链路一键诊断 (2026-04-19)
#
# 用法:
#   在 ECS 上直接跑: bash healthcheck_wave13.sh
#   从 Mac 跑:  sshpass -p 'WxAgent2026_Secure!Xy7K' ssh root@120.26.208.212 \
#               'bash -s' < scripts/healthcheck_wave13.sh
#
# 输出每环 PASS/FAIL · 最后给修复提示
# 不改任何状态 · 只读

set +e
RED='\033[31m'; GRN='\033[32m'; YEL='\033[33m'; NC='\033[0m'
PASS=0; FAIL=0
pass() { echo -e "${GRN}✅ $1${NC}"; PASS=$((PASS+1)); }
fail() { echo -e "${RED}❌ $1${NC}  → $2"; FAIL=$((FAIL+1)); }
warn() { echo -e "${YEL}⚠️  $1${NC}"; }

ACCOUNT_ID="wx_ant_0001_0ee870"
AUTH_KEY=$(sqlite3 /root/wechat_agent/data/wechat_agent.db \
  "SELECT auth_key FROM wx_account WHERE account_id='$ACCOUNT_ID'" 2>/dev/null)
WXID=$(sqlite3 /root/wechat_agent/data/wechat_agent.db \
  "SELECT wxid FROM wx_account WHERE account_id='$ACCOUNT_ID'" 2>/dev/null)
REDIS_PASS="73e4b480710b7545e90b0bd3"
FRP_PORT=$(sqlite3 /root/wechat_agent/data/wechat_agent.db \
  "SELECT frp_port FROM wx_account WHERE account_id='$ACCOUNT_ID'" 2>/dev/null)

echo "======== Wave 13 Health Check · $(date '+%F %T') ========"
echo "account_id = $ACCOUNT_ID"
echo "wxid       = $WXID"
echo "auth_key   = $AUTH_KEY"
echo "frp_port   = $FRP_PORT"
echo

# ─── 环 1: Docker 容器(wxpadpro + redis + mysql) ──────────────────────────
echo "[1/6] Docker 容器 · WxPadPro + Redis + MySQL"
RUN_CNT=$(docker ps --filter 'name=wxpad' --format '{{.Names}}' 2>/dev/null | wc -l)
if [ "$RUN_CNT" -ge 3 ]; then
    pass "3 容器 active: wxpadpro / redis / mysql"
else
    fail "容器缺失 · 现跑 $RUN_CNT/3" "cd /root/wechat_agent/deploy && docker-compose up -d"
fi

# ─── 环 2: frp 隧道(客户 PC → ECS) ─────────────────────────────────────────
echo
echo "[2/6] frp 隧道 · 客户 PC frpc → ECS frps"
FRPS_UP=$(systemctl is-active frps 2>/dev/null)
if [ "$FRPS_UP" = "active" ]; then
    pass "frps systemd active (port 7000)"
else
    fail "frps 未跑" "systemctl restart frps"
fi

PORT_LISTEN=$(ss -tln 2>/dev/null | grep -c ":$FRP_PORT")
if [ "$PORT_LISTEN" -ge 1 ]; then
    pass "frp 反向端口 $FRP_PORT listening (客户 frpc 已连)"
else
    fail "frp $FRP_PORT 无 listener · 客户 frpc 掉了" \
         "让客户重开桌面 Start.bat (frpc.exe 黑窗口保持开)"
fi

# ─── 环 3: socks5 proxy 走客户家 IP 出公网 ────────────────────────────────
echo
echo "[3/6] socks5 proxy · 走客户家 IP 出公网"
PUBLIC_IP=$(curl -s --socks5 127.0.0.1:$FRP_PORT --max-time 10 https://ifconfig.me 2>/dev/null)
if [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "120.26.208.212" ]; then
    pass "proxy 出口 IP = $PUBLIC_IP (非 ECS)"
else
    fail "proxy 走不通 · 出口=$PUBLIC_IP" \
         "检查 frpc 日志 · 检查客户家 socks5(1080) 是否开"
fi

# ─── 环 4: WxPadPro 登录状态 ──────────────────────────────────────────────
echo
echo "[4/6] WxPadPro 登录状态"
LOGIN=$(curl -s "http://127.0.0.1:8059/login/GetLoginStatus?key=$AUTH_KEY" 2>/dev/null)
STATE=$(echo "$LOGIN" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('Data',{}).get('loginState',0))" 2>/dev/null)
if [ "$STATE" = "1" ]; then
    pass "loginState=1 · 号在线"
else
    fail "loginState=$STATE · 号不在线" \
         "重扫码: POST /v1/wxpad/qr/$ACCOUNT_ID"
fi

# ─── 环 5: server + sync_loop + Redis 可达 ────────────────────────────────
echo
echo "[5/6] server + sync_loop + Redis"
SERVER_UP=$(systemctl is-active wechat-agent 2>/dev/null)
if [ "$SERVER_UP" = "active" ]; then
    pass "wechat-agent systemd active (port 8327)"
else
    fail "server 挂了" "systemctl restart wechat-agent"
fi

HEALTH=$(curl -s -m 5 http://127.0.0.1:8327/v1/health 2>/dev/null)
if echo "$HEALTH" | grep -q hermes_reachable; then
    pass "/v1/health OK"
else
    fail "/v1/health 无响应" "tail /root/wechat_agent/logs/server.err.log"
fi

REDIS_LEN=$(docker exec deploy-wxpad_redis-1 redis-cli -a "$REDIS_PASS" --no-auth-warning \
    -n 1 LLEN "${AUTH_KEY}_syncMsg" 2>/dev/null)
if [ -n "$REDIS_LEN" ]; then
    pass "Redis syncMsg 队列长度 = $REDIS_LEN"
else
    fail "Redis 读取失败" "检查 REDIS_PASSWORD / 容器状态"
fi

# 新 Redis AuthError 检测(最近 50 行)
AUTH_ERR=$(tail -50 /root/wechat_agent/logs/server.err.log 2>/dev/null | grep -c "AuthenticationError")
if [ "$AUTH_ERR" = "0" ]; then
    pass "sync_loop Redis 无 AuthError"
else
    fail "sync_loop Redis AuthError × $AUTH_ERR" \
         "grep REDIS_PASSWORD /root/wechat_agent/.env · 必须有值"
fi

# ─── 环 6: 端到端 · /v1/inbound 真 LLM ────────────────────────────────────
echo
echo "[6/6] /v1/inbound 端到端 LLM"
TS=$(date +%s)
REPLY=$(curl -s -X POST http://127.0.0.1:8327/v1/inbound \
    -H "Content-Type: application/json" \
    -d "{\"tenant_id\":\"tenant_0001\",\"chat_id\":\"hc_$TS\",\"sender_id\":\"hc_u_$TS\",\"sender_name\":\"healthcheck\",\"text\":\"在吗\",\"timestamp\":$TS,\"msg_type\":\"text\"}" 2>/dev/null)
TEXT=$(echo "$REPLY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('text',''))" 2>/dev/null)
ROUTE=$(echo "$REPLY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('model_route',''))" 2>/dev/null)
if [ -n "$TEXT" ] && [ ${#TEXT} -gt 3 ]; then
    pass "LLM 真返: route=$ROUTE · text=${TEXT:0:40}"
else
    fail "LLM 返空/失败" "检查 MINIMAX_API_KEY + server.err.log"
fi

# ─── 汇总 ──────────────────────────────────────────────────────────────────
echo
echo "======== 汇总 · PASS=$PASS FAIL=$FAIL ========"
if [ "$FAIL" = "0" ]; then
    echo -e "${GRN}🟢 全绿 · 端到端可用 · 让客户小号发消息测实时自动回${NC}"
    exit 0
else
    echo -e "${RED}🔴 $FAIL 项失败 · 按上面 → 修复${NC}"
    exit 1
fi
