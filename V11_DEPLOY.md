# V11 部署手册 — WeChatPadPro 双层架构

> 阿里云 ECS + 客户机 SOCKS5 出口防风控. 一次性通过.

## 阿里云真状态 (2026-05-03 CDP 真核)

| 资源 | 真状态 |
|------|--------|
| 主账号 | aliyun5407142119 (ernsftmeieyer540@gmail.com) |
| 区域 | 华东2 (上海) |
| 现有 ECS | **i-uf6gbgj8zcaegttv2zpr (gn7i-c8g1.2xlarge GPU A10)** |
| 公网 IP | 8.153.106.103 |
| 状态 | **已停止 (余额不足!)** ← 用户必先充钱 |
| OS | Ubuntu 22.04 + NVIDIA GPU 驱动 + CUDA |
| 规格 | 8 vCPU / 30 GiB / GPU NVIDIA A10 |
| 计费 | 按量 ¥9.6376/h (训练时启, 完了关) |

## 真架构: 训练 + 推理 分开

```
┌─────────────────────────────────────────────────────────────┐
│ 阿里云 ECS (上海)                                            │
├─────────────────────────────────────────────────────────────┤
│  ① 推理 ECS (常驻 ~¥95/月)  ← V11 新开                       │
│     ecs.t6-c4m2 (2C4G) 或复用现有 GPU 实例                  │
│     ├── WeChatPadPro Docker (linux-amd64 22MB)              │
│     ├── wechat_agent server (FastAPI :8327)                 │
│     ├── MySQL + Redis (容器内)                              │
│     └── 走客户机 SOCKS5 出口 ← 防风控核心                   │
│                                                              │
│  ② 训练 ECS (按需, 用完关)                                   │
│     gn7i-c8g1.2xlarge GPU A10 (现有 i-uf6gbgj8zcaegttv2zpr) │
│     ├── LLaMA-Factory + Unsloth                             │
│     ├── 训练 LoRA (47 + 190 衍生 = 237 ChatML pair)         │
│     └── 完成后 SCP 模型到 推理 ECS                          │
└─────────────────────────────────────────────────────────────┘
                ↑ 经客户家用 IP
                │
┌─────────────────────────────────────────────────────────────┐
│ 客户机 wechat_agent.exe (5MB)                                │
│  ├── SOCKS5 server (:1080) ← 走客户家用 IP 出口             │
│  ├── 扫码 UI (tkinter, 启动时弹二维码)                       │
│  └── 心跳上报 ECS (告诉服务"我在线")                         │
└─────────────────────────────────────────────────────────────┘
```

**关键**: 训练 (GPU) 和推理 (CPU) 分开两个实例.

## 测试 vs 生产 — 真分阶段

### 阶段 0: 测试 (现在 — 单客户 lian)
- **复用 GPU 实例** i-uf6gbgj8zcaegttv2zpr 跑 WeChatPadPro Docker
- 30G 内存绰绰有余
- 启停灵活
- 测完关 (省钱)

### 阶段 1: 生产 (1+ 客户)
- **新开 2C4G 普通 ECS** (¥95/月固定)
- 24x7 跑 WeChatPadPro + server
- GPU 实例只在训练时启

### 阶段 2: 多客户 SaaS
- 每客户独立 WeChatPadPro 容器 (Docker namespace)
- 共享 server + LLM API
- 弹性扩 (k8s)

## V11 部署步骤 (用户充钱后执行)

### Step 1: 启 GPU 实例 (临时跑 V11 测试)
```bash
# 阿里云控制台启 i-uf6gbgj8zcaegttv2zpr
# SSH 进 ECS (用 ~/lian.pem)
ssh -i ~/lian.pem root@8.153.106.103
```

### Step 2: 装 Docker
```bash
# Ubuntu 22.04 装 docker-compose
curl -fsSL https://get.docker.com | bash
apt install -y docker-compose-plugin
```

### Step 3: 部 WeChatPadPro
```bash
# 下 v2.01 linux-amd64
mkdir -p /opt/wechatpad && cd /opt/wechatpad
wget https://github.com/WeChatPadPro/WeChatPadPro/releases/download/v2.01/wechatpadpro_vios18.61-861_20250822_linux-amd64.zip
unzip wechatpadpro_vios18.61-861_20250822_linux-amd64.zip

# docker-compose.yml (从 GitHub repo deploy/ 拷)
git clone https://github.com/WeChatPadPro/WeChatPadPro.git
cd WeChatPadPro/deploy
# 改 .env 配 ADMIN_KEY (随机字符串)
docker-compose up -d
```

### Step 4: 配 SOCKS5 出口
```yaml
# docker-compose.yml 加 environment:
environment:
  - HTTP_PROXY=socks5://CLIENT_IP:1080
  - HTTPS_PROXY=socks5://CLIENT_IP:1080
# CLIENT_IP = 客户机公网 IP (启动时 client.exe 心跳上报)
```

### Step 5: 客户机 .exe 改 SOCKS5
```python
# client/main.py 改:
# - 装 PySocks (pip install pysocks)
# - 启 SOCKS5 server :1080
# - tkinter 显示扫码 UI
# - 删 wxauto4 路线 (V11 不需要)
```

### Step 6: server 集成 WeChatPadPro REST API
```python
# server/wechatpad_engine.py:
import requests

WECHATPAD_BASE = "http://127.0.0.1:8080"  # WeChatPadPro 容器
TOKEN = os.environ['WECHATPAD_TOKEN']  # 启动时获取

def send_message(chat: str, text: str):
    return requests.post(
        f"{WECHATPAD_BASE}/v1/message/SendTextMsg",
        headers={"X-GEWE-TOKEN": TOKEN},
        json={"toUser": chat, "content": text}
    )

def receive_messages():
    # WeChatPadPro 推送回调到 server
    # FastAPI endpoint /webhook/wechatpad 接收
    pass
```

## 真养号 SOP (客户必读)

| 阶段 | 限制 | 真原因 |
|------|------|--------|
| 第 1 周 (新号) | **不加群**, 慢速 (1 分钟 1 条) | issue #67 维护者真嘱 "養號先" |
| 第 2-4 周 | 加群慢慢加 (每天 < 5 个) | 风控对老号宽松 |
| 长期 | 不发重复内容, 不超 50 条/小时 | 风控触发线 |

## 真链接

- WeChatPadPro release: https://github.com/WeChatPadPro/WeChatPadPro/releases
- Docker compose: https://github.com/WeChatPadPro/WeChatPadPro/tree/main/deploy
- 在线 demo: https://wx.knowhub.cloud/ (默认密钥 28d21d0f9748172c970ba4c208af5564)
- Telegram: https://t.me/+LK0JuqLxjmk0ZjRh

## 真阻塞 (用户必做)

⚠️ **现在阻塞**:
1. 阿里云充钱 (现有 GPU 实例余额不足停了)
2. 充钱后我立即推 Step 1-6

⚠️ **未真测 + 真陷阱**:
- WeChatPadPro Docker SOCKS5 出口配置 (需 ECS 真跑才能验)
- 客户机在家庭 NAT 后, ECS **真不能直连**客户 SOCKS5 → 必反向通道:
  - 选 1: **chisel reverse** (轻量, 单二进制, 跨平台) ⭐ 推荐
  - 选 2: v2ray/Xray reverse (功能多, 重)
  - 选 3: frp socks 协议 (国内主流)
- 客户机.exe 内嵌 chisel client, 启动时主动连 ECS, ECS 通过反向通道走客户 IP 出口

## 真反向通道架构 (关键修正)

```
客户机 .exe                          ECS
  └── chisel client ────主动连──→ chisel server :7000
       (走客户家用 IP)                   ↓
                                     SOCKS5 :1080 (本地)
                                          ↓
                                     WeChatPadPro 走 :1080 出口
                                          ↓ (经客户家 IP)
                                     微信服务器看到客户家 IP ✅
```

chisel 真命令:
```bash
# ECS 端
./chisel server --port 7000 --auth user:pass --reverse
# 客户机端
./chisel client --auth user:pass ECS_IP:7000 R:1080:socks
# (R = reverse, ECS 上的 :1080 经客户机出口)
```
