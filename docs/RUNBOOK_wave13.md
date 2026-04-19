# Wave 13 · 微信自动回复 · 运维手册

> 最后更新: 2026-04-19 · 真端到端跑通

## 架构 6 环

```
[1 小号发消息] → [2 WxPadPro Docker 收] → [3 Redis syncMsg 队列]
                                              ↓
[6 小号收 AI 回复] ← [5 SendText via socks5://frp_port] ← [4 sync_loop → /v1/inbound → MiniMax]
                     ↑                                         ↑
                     └── 客户家 frpc(外出流量走这)             └── 水位线 = create_time
```

## 一键健康检查

```bash
# 在 ECS 上:
bash /root/wechat_agent/scripts/healthcheck_wave13.sh

# 从 Mac:
sshpass -p 'WxAgent2026_Secure!Xy7K' ssh root@120.26.208.212 \
  'bash -s' < scripts/healthcheck_wave13.sh
```

全绿 = 端到端可用。某环红 = 按脚本提示修。

## ECS 访问

```
host: 120.26.208.212
user: root
pass: WxAgent2026_Secure!Xy7K
wd:   /root/wechat_agent
```

## 症状对照表

| 症状 | 最可能根因 | 定位命令 | 修复 |
|---|---|---|---|
| 小号发消息客户没回 | frpc 断 / sync_loop 挂 / LLM 返空 | `healthcheck_wave13.sh` | 看脚本提示 |
| WxPadPro 返 `Code 300 账号离线自动上线失败` | socks5 proxy 没连通(41080 no listener) | `ss -tln \| grep 41080` | 客户重开 Start.bat |
| 返空字串 / 很久没回 | MiniMax M2.7 thinking 吃光 max_tokens | `grep stop_reason logs/server.err.log` | max_tokens 必 ≥ 1500(已修) |
| sync_loop 不拉消息 | last_msg_id 水位线超过所有新消息 new_msg_id | 对比 DB last_msg_id 和 Redis 最新 ct | 水位线改 create_time(已修) |
| `redis.exceptions.AuthenticationError` | .env 缺 REDIS_PASSWORD / EnvironmentFile 未重载 | `cat /proc/$(pgrep -f uvicorn)/environ \| grep REDIS` | 补 .env · systemctl restart |
| 端口 8327 `address already in use` | 野生 uvicorn 没被 systemd 管 | `pgrep -af uvicorn` | 杀野 PID · systemctl restart |
| 回复太慢(>10s) | `_compute_reply_latency` clip 太大 | 看 `⏳ wait Xs` log | 调 `[2.0, 4.0]` 已是体验档 |
| 回复太快可能封号 | 拟真延迟 < 2s 不够 | 看 `lat=X` log | 最低必须 ≥ 2s |

## 关键文件

| 文件 | 职责 |
|---|---|
| `server/wxpadpro_bridge.py` | sync_loop · wxpad_send_text · _dispatch_reply · 水位线 create_time |
| `server/llm_clients.py` | MiniMaxTokenPlanClient._chat_anthropic · max_tokens=max(x+1000,1500) |
| `server/main.py` | /v1/inbound 入口 · 调 ReplyGenerator |
| `server/generator.py` | AI 路由: MiniMax M2.7 / 302.AI DeepSeek V4 |
| `/etc/systemd/system/wechat-agent.service` | server 守护 · EnvironmentFile=/root/wechat_agent/.env |
| `/etc/systemd/system/frps.service` | frps 守护 · 端口 7000 |
| `/root/wechat_agent/.env` | 所有环境变量单一来源 |

## 必须在 .env 里的 env(缺一会断环)

```bash
MINIMAX_API_KEY=sk-cp-...         # 否则 LLM mock
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=1
REDIS_PASSWORD=73e4b480710b7545e90b0bd3   # 否则 AuthError
WXPADPRO_BASE_URL=http://127.0.0.1:8059
WXPADPRO_ADMIN_KEY=12e0c960a3e2e0cf27e6fcc56216cc817d125f1a67d997a799416ac72d75a94e
FRP_SERVER_ADDR=120.26.208.212
FRP_SERVER_PORT=7000
FRP_SHARED_TOKEN=wxa-poc-2026-secret
BAIYANG_HERMES_MOCK=false
```

## 部署改动流程

```bash
# Mac 本地改完 · 测通
python3.11 -m pytest tests/ -x -q -k "wxpad or wave13"

# scp 到 ECS
sshpass -p 'WxAgent2026_Secure!Xy7K' scp \
  server/<改动文件>.py \
  root@120.26.208.212:/root/wechat_agent/server/

# ECS 重启 systemd
sshpass -p 'WxAgent2026_Secure!Xy7K' ssh root@120.26.208.212 \
  'systemctl restart wechat-agent && sleep 4 && systemctl is-active wechat-agent'

# 一键诊断
sshpass -p 'WxAgent2026_Secure!Xy7K' ssh root@120.26.208.212 \
  'bash -s' < scripts/healthcheck_wave13.sh
```

## 三大踩坑(绝不重犯)

### 踩坑 1 · MiniMax M2.7-highspeed thinking 吃光 max_tokens

M2.7-highspeed 是推理模型 · 强制输出 `thinking` 块 + `text` 块 · thinking 吃 200-500 tokens。若 `max_tokens=300` 被 thinking 吃光 · text 块返空 · `stop_reason=max_tokens` · 客户看"没回"。

**修**: `server/llm_clients.py::_chat_anthropic` · `effective_max = max(max_tokens + 1000, 1500)`.

### 踩坑 2 · sync_loop 用 new_msg_id 做水位线

`new_msg_id` 不单调 · 不同 msg_type(1/10002/51) 从不同 ID 池分配 · 新文本消息 ID 可能 < 旧系统消息 ID。用作水位线会漏消息。

**修**: 改用 `create_time` (Unix 秒 · 严格单调) 做水位线 · `server/wxpadpro_bridge.py::_sync_loop`。

### 踩坑 3 · systemd 启动丢 env

野生 `nohup uvicorn` process 的 env 在 `/proc/PID/environ` 里 · 但只是那次跑起来时的。systemd `EnvironmentFile=.env` 只读 .env · 若 .env 缺 REDIS_PASSWORD 等 · systemd 重启后环境变量丢 · sync_loop 连 Redis `AuthError`。

**修**: 所有运行期 env 必须落 .env · 唯一来源。

## 进一步可做(非当前阻塞)

- 客户端 frpc 自动重连 + 心跳上报(现手动 Start.bat)
- Docker Compose 把 frps 也拉进来 · 统一 `docker-compose up` 管控
- `/v1/inbound` 收到 MessageModel.msg_id 去重后 · 应 short-circuit 不重复 dispatch
- 监控: 每 60s 自动跑 healthcheck · 红灯发告警
