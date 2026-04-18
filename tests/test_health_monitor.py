"""F6 · 反封号引擎测试 · 5 维度评分 + 三档响应 + on_red 回调。"""

from __future__ import annotations

import pytest

from server.health_monitor import (
    HealthMonitor,
    composite_score,
    health_level,
    quota_for_level,
    score_metric,
)


# ─── 单维度评分 ──────────────────────────────────────────────────────────

def test_score_friend_pass_rate_perfect():
    assert score_metric("friend_pass_rate", 0.85) == 100.0
    assert score_metric("friend_pass_rate", 1.0) == 100.0  # 不超分
    assert score_metric("friend_pass_rate", 0.425) == 50.0


def test_score_msg_similarity_inverted():
    assert score_metric("msg_similarity_avg", 0.0) == 100.0  # 0% 重复 = 满分
    assert score_metric("msg_similarity_avg", 0.6) == 0.0    # 60% 重复 = 0
    assert score_metric("msg_similarity_avg", 0.3) == 50.0


def test_score_ip_switches_penalty():
    assert score_metric("ip_switches", 0) == 100.0
    assert score_metric("ip_switches", 5) == 0.0    # 100 - 5*20
    assert score_metric("ip_switches", 10) == 0.0   # 仍是 0 · 不负


def test_score_unknown_metric_neutral():
    assert score_metric("unknown_x", 1.0) == 50.0


# ─── 综合分 ──────────────────────────────────────────────────────────────

def test_composite_empty_metrics_assumed_healthy():
    assert composite_score({}) == 100.0


def test_composite_all_perfect():
    metrics = {
        "friend_pass_rate": 0.85,
        "msg_similarity_avg": 0.0,
        "reply_rate": 0.4,
        "ip_switches": 0,
        "heartbeat_anomaly": 0,
    }
    assert composite_score(metrics) == 100.0


def test_composite_all_zero():
    metrics = {
        "friend_pass_rate": 0.0,
        "msg_similarity_avg": 0.6,
        "reply_rate": 0.0,
        "ip_switches": 5,
        "heartbeat_anomaly": 4,
    }
    assert composite_score(metrics) == 0.0


# ─── 等级 ────────────────────────────────────────────────────────────────

def test_level_thresholds():
    assert health_level(95) == "green"
    assert health_level(80) == "green"
    assert health_level(75) == "yellow"
    assert health_level(60) == "yellow"
    assert health_level(59) == "red"
    assert health_level(0) == "red"


def test_quota_throttle_by_level():
    assert quota_for_level("green", 100) == 100
    assert quota_for_level("yellow", 100) == 50
    assert quota_for_level("red", 100) == 0


# ─── HealthMonitor · DB 集成 ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_and_evaluate_green(temp_db):
    mon = HealthMonitor()
    await mon.record("tenant_0001", "primary", "friend_pass_rate", 0.9)
    await mon.record("tenant_0001", "primary", "msg_similarity_avg", 0.1)
    snap = await mon.evaluate("tenant_0001", "primary")
    assert snap.level == "green"
    assert snap.score >= 80
    assert snap.paused_until is None


@pytest.mark.asyncio
async def test_record_and_evaluate_red(temp_db):
    mon = HealthMonitor()
    await mon.record("tenant_0001", "primary", "friend_pass_rate", 0.1)
    await mon.record("tenant_0001", "primary", "msg_similarity_avg", 0.6)
    await mon.record("tenant_0001", "primary", "ip_switches", 5)
    snap = await mon.evaluate("tenant_0001", "primary")
    assert snap.level == "red"
    assert snap.paused_until is not None
    assert snap.daily_quota_override == 0


@pytest.mark.asyncio
async def test_red_triggers_callback(temp_db):
    fired = []

    async def on_red(tenant_id, account_id, snap):
        fired.append((tenant_id, account_id, snap.level))

    mon = HealthMonitor(on_red=on_red)
    await mon.record("tenant_0001", "primary", "friend_pass_rate", 0.0)
    await mon.record("tenant_0001", "primary", "msg_similarity_avg", 0.6)
    await mon.evaluate("tenant_0001", "primary")
    assert len(fired) == 1
    assert fired[0][2] == "red"


@pytest.mark.asyncio
async def test_manual_recover_resets(temp_db):
    mon = HealthMonitor()
    await mon.record("tenant_0001", "primary", "friend_pass_rate", 0.0)
    await mon.evaluate("tenant_0001", "primary")
    snap_before = await mon.get_status("tenant_0001", "primary")
    assert snap_before.level == "red"

    ok = await mon.manual_recover("tenant_0001", "primary")
    assert ok
    snap_after = await mon.get_status("tenant_0001", "primary")
    assert snap_after.level == "green"
    assert snap_after.paused_until is None


@pytest.mark.asyncio
async def test_tick_all_evaluates_watched(temp_db):
    mon = HealthMonitor()
    mon.watch("tenant_0001", "primary")
    mon.watch("tenant_0002", "primary")
    n = await mon.tick_all()
    assert n == 2


@pytest.mark.asyncio
async def test_tenant_isolation(temp_db):
    mon = HealthMonitor()
    await mon.record("tenant_A", "primary", "friend_pass_rate", 0.0)
    await mon.record("tenant_B", "primary", "friend_pass_rate", 0.9)
    a = await mon.evaluate("tenant_A", "primary")
    b = await mon.evaluate("tenant_B", "primary")
    assert a.level == "red"
    assert b.level == "green"
