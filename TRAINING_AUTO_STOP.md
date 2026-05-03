# 训练自动关机 + 数据保存方案

> 解决: 训练完忘关 → 实例 24h 空跑烧钱 (用户已烧 100). 真自动化 = 训练完 5 分钟内自动停.

## 真根因

- gn7i-c8g1.2xlarge 按量 **¥9.6/h × 24h = ¥231/天**
- 训练任务真完成后, **进程退出但实例还在**
- 用户不监控 → 烧到余额不足才知

## 真四层防护 (从弱到强)

### 层 1: 训练脚本末尾自动关机 ⭐ 最简单

```bash
#!/bin/bash
# /root/train.sh — 训练入口

set -e

# 1. 保存 checkpoint 到 OSS
ossutil cp -r /root/checkpoints/ oss://wechat-agent-train/$(date +%Y%m%d_%H%M)/

# 2. 训练
python3 train_lora.py --config qwen3_8b.yaml

# 3. 训练完保存模型到 OSS
ossutil cp -r /root/output/ oss://wechat-agent-train/output_$(date +%Y%m%d_%H%M)/

# 4. 5 分钟后自动关机 (留缓冲, 万一脚本异常)
echo "训练完, 5 分钟后自动 shutdown..."
sudo shutdown -h +5
```

**Why**: 进程退出 → bash 跑 shutdown → OS 关机.
**How**: `bash train.sh` 完了无人值守.

### 层 2: ECS 元数据 — OS 关机时阿里云自动停实例 ⭐⭐

```bash
# 阿里云 CLI 配 ECS 实例 ShutdownBehavior
aliyun ecs ModifyInstanceAttribute \
  --InstanceId i-uf6gbgj8zcaegttv2zpr \
  --InstanceChargeType PostPaid \
  --SystemDisk.Category cloud_essd

# 关键: ECS 控制台 → 实例 → 停机模式 → "Stop & Save (节省停机模式)"
# 一旦 OS 关机, 阿里云自动停实例 + 切节省模式 (vCPU/内存/GPU 不计费)
```

**Why**: 避免 OS 关了但实例没停 (vCPU/内存还在算钱).
**How**: 控制台或 API 设默认 ShutdownBehavior=StopCharging.

### 层 3: cron 监控 GPU 利用率, 0% 持续 30min 自动关 ⭐⭐⭐

```bash
# /etc/cron.d/auto_shutdown_idle (每 5 min 跑)
*/5 * * * * root /root/check_idle.sh

# /root/check_idle.sh
#!/bin/bash
GPU_UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits | head -1)
IDLE_FILE=/tmp/gpu_idle_count
if [ "$GPU_UTIL" -lt 5 ]; then
  count=$(cat $IDLE_FILE 2>/dev/null || echo 0)
  count=$((count + 1))
  echo $count > $IDLE_FILE
  if [ $count -ge 6 ]; then  # 6 × 5min = 30min
    echo "GPU idle 30min, auto shutdown" | logger
    sudo shutdown -h now
  fi
else
  echo 0 > $IDLE_FILE
fi
```

**Why**: 真兜底, 即使训练脚本没 shutdown, GPU 闲 30 分钟也自动关.
**How**: cron 每 5 min 跑, 计数到 6 触发关机.

### 层 4: 余额告警 — 防极端情况 ⭐⭐⭐⭐

```
阿里云控制台:
1. 费用中心 → 用量预警
2. 预算 ¥50, 触发短信通知 lian 手机
3. 余额 < ¥30, 自动停所有按量实例 (阿里云原生功能)
```

**Why**: 保险丝, 万一前 3 层都失效, 钱不会烧光.
**How**: 阿里云控制台 1 次配置.

## 真数据持久化方案

| 数据 | 方案 |
|------|------|
| 训练 checkpoint | OSS bucket `wechat-agent-train/checkpoints/` (每 100 步存) |
| 训练完模型 | OSS bucket `wechat-agent-train/output_<ts>/` (压缩后) |
| 训练日志 | OSS bucket `wechat-agent-train/logs/` |
| 训练数据 (47 + 190 ChatML) | OSS bucket `wechat-agent-train/data/` (一次上传, 实例下载) |

**OSS bucket 创建** (¥0.12/GB/月):
```bash
aliyun oss mb oss://wechat-agent-train --region cn-shanghai
# 上传训练数据
ossutil cp -r ~/wechat_agent/data/ oss://wechat-agent-train/data/
```

实例释放/启动失败也不丢, OSS 真持久.

## 真训练流水 (无人值守)

```
1. lian 手动启动 GPU 实例 (阿里云控制台, 1 click)
2. SSH 进入: ssh -i ~/lian.pem root@<新IP>
3. 跑训练: nohup bash /root/train.sh > /var/log/train.log 2>&1 &
4. lian 关掉 SSH, 去做别的
5. 训练 ~1h 完成 → 自动保存 OSS → 5min 后 shutdown
6. ECS 元数据 ShutdownBehavior=StopCharging → 实例自动停 + 节省停机
7. 第二天 lian 看 OSS 有新模型 = 训练完, 0 烧钱
```

## 真应急按钮

```bash
# 紧急强停 (从本机用 aliyun CLI)
aliyun ecs StopInstance \
  --InstanceId i-uf6gbgj8zcaegttv2zpr \
  --StoppedMode StopCharging \
  --ForceStop true
```

## 真预算 (优化后)

| 用途 | 真账 |
|------|------|
| 训练 1 次 (1h) | ¥10 |
| GPU 节省停机 (29 天) | ¥0.5/天 × 29 = ¥15 |
| OSS 存储 (10GB × 1 月) | ¥1.2 |
| **训练月成本** | **~¥30** ⭐ |

vs 当前 (普通停机仍按 ¥9.6/h):
- 不停: ¥231/天 × 30 = **¥6900/月** ❌
- 自动停: **¥30/月** ✅
- 真省 99.6%

## 真未实施 (待用户启实例后做)

- [ ] 配 ECS ShutdownBehavior=StopCharging (1 click)
- [ ] 创建 OSS bucket `wechat-agent-train`
- [ ] 装 ossutil + cron 配自动监控
- [ ] 写 train.sh 模板 (含 shutdown 末尾)
- [ ] 配阿里云余额告警 (短信 ¥50 阈值)
