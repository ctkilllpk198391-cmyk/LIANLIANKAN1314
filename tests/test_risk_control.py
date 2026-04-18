"""客户端 RiskController 测试 · 工作时间 + 配额。"""

from __future__ import annotations

from datetime import datetime

import pytest

from client.risk_control import RiskController, WorkSchedule
from shared.errors import QuotaExceededError, WorkhourViolationError


def test_workhour_inside():
    sched = WorkSchedule(start="09:00", end="21:00")
    assert sched.is_workhour(datetime(2026, 4, 15, 12, 0)) is True


def test_workhour_outside_morning():
    sched = WorkSchedule(start="09:00", end="21:00")
    assert sched.is_workhour(datetime(2026, 4, 15, 8, 0)) is False


def test_workhour_outside_evening():
    sched = WorkSchedule(start="09:00", end="21:00")
    assert sched.is_workhour(datetime(2026, 4, 15, 22, 0)) is False


def test_quota_default():
    rc = RiskController()
    rc.register("tenant_0001")
    assert rc.quota_remaining("tenant_0001") == 30


def test_quota_consume_decrements():
    rc = RiskController()
    rc.register("tenant_0001", daily_quota=5)
    now = datetime(2026, 4, 15, 12, 0)
    rc.consume("tenant_0001", now=now)
    assert rc.quota_remaining("tenant_0001") == 4


def test_quota_max_clamped():
    rc = RiskController()
    rc.register("tenant_0001", daily_quota=999)
    # 上限 150
    assert rc.quota_remaining("tenant_0001") == 150


def test_consume_blocks_outside_workhour():
    rc = RiskController()
    rc.register("tenant_0001")
    night = datetime(2026, 4, 15, 23, 0)
    with pytest.raises(WorkhourViolationError):
        rc.consume("tenant_0001", now=night)


def test_consume_blocks_quota_exhausted():
    rc = RiskController()
    rc.register("tenant_0001", daily_quota=1)
    noon = datetime(2026, 4, 15, 12, 0)
    rc.consume("tenant_0001", now=noon)
    with pytest.raises(QuotaExceededError):
        rc.consume("tenant_0001", now=noon)


def test_can_send_combines_workhour_and_quota():
    rc = RiskController()
    rc.register("tenant_0001", daily_quota=5)
    noon = datetime(2026, 4, 15, 12, 0)
    night = datetime(2026, 4, 15, 23, 0)
    assert rc.can_send("tenant_0001", noon) is True
    assert rc.can_send("tenant_0001", night) is False


def test_unregistered_tenant_lenient():
    rc = RiskController()
    # 未注册的 tenant 默认宽松（is_workhour 返回 True）
    assert rc.is_workhour("tenant_unknown", datetime(2026, 4, 15, 23, 0)) is True
