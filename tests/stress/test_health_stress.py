"""D2 · 反封号压测 · First Wave 收尾。

4 个压测场景：
  1. test_high_similarity_triggers_yellow_then_red    1000 条 metric · 30% 高相似度 → yellow/red · 降速
  2. test_ip_switches_force_red_and_failover          ip_switches=5 → red + failover 切 secondary
  3. test_follow_up_1000_concurrent_tick              1000 个 follow_up 全到点 · tick 批量处理不卡死
  4. test_health_no_metric_assumed_healthy            无 metric · evaluate → green + score=100
"""

from __future__ import annotations

import time
from typing import Optional

import pytest

from server.account_failover import AccountFailover
from server.follow_up import FollowUpEngine
from server.health_monitor import HealthMonitor
from server.models import FollowUpTask
from server.tenant import TenantManager
from shared.proto import TenantConfig


# ──────────────────────────────────────────────────────────────────────────────
# Helper：快速构造带双账号的 TenantManager（复用 test_account_failover.py 模式）
# ──────────────────────────────────────────────────────────────────────────────

def _mk_dual_account_tm(tenant_id: str = "stress_tenant") -> TenantManager:
    tm = TenantManager()
    tm._cache[tenant_id] = TenantConfig(
        tenant_id=tenant_id,
        boss_name="压测老板",
        accounts=[
            {"account_id": "acc_primary",   "role": "primary",   "wxid": "wx_p"},
            {"account_id": "acc_secondary",  "role": "secondary", "wxid": "wx_s"},
        ],
        active_account_id="acc_primary",
    )
    return tm


# ──────────────────────────────────────────────────────────────────────────────
# 1. 高相似度触发 yellow / red · 验证降速
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_high_similarity_triggers_yellow_then_red(temp_db):
    """1000 条 metric record · 30% 高相似度 → evaluate 触发 yellow 或 red · daily_quota_override 降速。"""
    mon = HealthMonitor(base_quota=100)
    tenant_id = "stress_t1"
    account_id = "primary"

    # 写 1000 条 metric record，模拟高频上报场景（直接批量插库，避免 time.time() 精度问题）
    # 策略：700 条低相似度（0.1）recorded_at = past，300 条高相似度（0.55）recorded_at = past+1
    # evaluate 按 recorded_at DESC 取最新，高相似度时间戳更新 → 一定被选中
    from server.db import session_scope as _ss
    from server.models import AccountHealthMetric as _AHM

    past = int(time.time()) - 10  # 稍早时间
    now  = past + 5               # 高相似度用更新的时间戳，确保 DESC 排在前

    # 批量插入 700 条低相似度（较早时间戳）
    async with _ss() as sess:
        for i in range(700):
            sess.add(_AHM(
                tenant_id=tenant_id,
                account_id=account_id,
                metric_name="msg_similarity_avg",
                value=0.1,
                recorded_at=past,
            ))

    # 批量插入 300 条高相似度（更新时间戳 → evaluate 取最新 = 0.55）
    async with _ss() as sess:
        for i in range(300):
            sess.add(_AHM(
                tenant_id=tenant_id,
                account_id=account_id,
                metric_name="msg_similarity_avg",
                value=0.55,
                recorded_at=now,
            ))

    snap = await mon.evaluate(tenant_id, account_id)

    # 最新值为 0.55 → score_metric("msg_similarity_avg", 0.55) ≈ 8.3 → yellow 或 red
    assert snap.level in ("yellow", "red"), f"expected yellow/red, got {snap.level} (score={snap.score})"

    # 验证降速：daily_quota_override 必须非 None 且 < base_quota
    assert snap.daily_quota_override is not None, "降速 override 应被设置"
    assert snap.daily_quota_override < 100, f"quota 应降速，got {snap.daily_quota_override}"


# ──────────────────────────────────────────────────────────────────────────────
# 2. IP 切换 5 次 → red + failover 切到 secondary
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ip_switches_force_red_and_failover(temp_db):
    """ip_switches=5 → score=0 → red · on_red 回调触发 auto_failover → 切到 secondary。"""
    tenant_id = "stress_t2"
    failover_calls: list[str] = []

    tm = _mk_dual_account_tm(tenant_id)

    # 先建 HealthMonitor 空壳，稍后注入 on_red
    mon = HealthMonitor(base_quota=100)
    fo = AccountFailover(tm, mon)

    async def on_red(t_id: str, a_id: str, snap):
        new_acc = await fo.auto_failover(t_id, a_id, reason="health_red_stress")
        if new_acc:
            failover_calls.append(new_acc)

    mon.on_red = on_red

    # ip_switches=5 → score_metric = max(0, 100 - 5*20) = 0 → 单维度综合分 = 0 → red
    await mon.record(tenant_id, "acc_primary", "ip_switches", 5)
    snap = await mon.evaluate(tenant_id, "acc_primary")

    assert snap.level == "red", f"expected red, got {snap.level} (score={snap.score})"
    assert snap.paused_until is not None
    assert snap.daily_quota_override == 0

    # 验证 failover 已触发并切到 secondary
    assert len(failover_calls) == 1, f"failover 应触发一次，got {failover_calls}"
    assert failover_calls[0] == "acc_secondary"
    assert fo.get_active_account_id(tenant_id) == "acc_secondary"


# ──────────────────────────────────────────────────────────────────────────────
# 3. 1000 个 follow_up 同时到点 · tick 批量处理不卡死
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_follow_up_1000_concurrent_tick(temp_db):
    """schedule 1000 个 follow_up · scheduled_at 全设为过去 · tick 批量 100 处理不卡死 · 最终清空。"""
    tenant_id = "stress_t3"
    send_calls: list[str] = []

    async def mock_send(t_id: str, chat_id: str, text: str, task_id: str) -> bool:
        send_calls.append(task_id)
        return True

    engine = FollowUpEngine(send_callback=mock_send)

    # schedule 1000 个 task，scheduled_at 全部设为过去（现在 - 1）
    past = int(time.time()) - 1
    from server.db import session_scope

    # 批量直接插入 DB，不走 schedule()（schedule() 用 TYPE_DELAYS 自动算未来时间）
    from server.models import FollowUpTask as FUTask
    import uuid

    async with session_scope() as session:
        for i in range(1000):
            session.add(FUTask(
                task_id=f"fu_stress_{i:04d}",
                tenant_id=tenant_id,
                chat_id=f"chat_{i:04d}",
                sender_name="压测",
                task_type="unpaid_30min",
                scheduled_at=past,
                status="pending",
                template_id="unpaid_30min",
                context_json="{}",
                created_at=past,
            ))

    # 第一次 tick：应处理 limit=100 条
    processed_first = await engine.tick()
    assert processed_first == 100, f"第一次 tick 应处理 100 条，got {processed_first}"
    assert len(send_calls) == 100

    # 继续 tick 直到清空（最多 15 次防死循环）
    total_processed = processed_first
    for _ in range(15):
        n = await engine.tick()
        total_processed += n
        if n == 0:
            break

    # 全部 1000 条都处理完
    assert total_processed == 1000, f"应总共处理 1000 条，got {total_processed}"
    assert len(send_calls) == 1000


# ──────────────────────────────────────────────────────────────────────────────
# 4. 无 metric · evaluate → green · score=100 · 不报错不卡死
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_no_metric_assumed_healthy(temp_db):
    """不 record 任何 metric · evaluate 应返回 green · score=100 · 正常完成不卡死。"""
    mon = HealthMonitor(base_quota=100)
    snap = await mon.evaluate("stress_t4", "primary")

    assert snap.level == "green", f"无 metric 应为 green，got {snap.level}"
    assert snap.score == 100.0, f"无 metric 分数应为 100，got {snap.score}"
    assert snap.daily_quota_override is None
    assert snap.paused_until is None
