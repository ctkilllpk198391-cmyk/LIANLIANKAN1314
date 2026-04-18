"""客户端风控 · 工作时间 + 日配额 + 心跳调度。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time as dtime
from typing import Optional

from shared.const import (
    DAILY_QUOTA_MAX,
    DAILY_QUOTA_NEW,
    DAILY_QUOTA_SEASONED,
    WORKHOUR_DEFAULT_END,
    WORKHOUR_DEFAULT_START,
)
from shared.errors import QuotaExceededError, WorkhourViolationError

logger = logging.getLogger(__name__)


@dataclass
class WorkSchedule:
    start: str = WORKHOUR_DEFAULT_START
    end: str = WORKHOUR_DEFAULT_END

    def is_workhour(self, now: Optional[datetime] = None) -> bool:
        now = now or datetime.now()
        s_h, s_m = (int(x) for x in self.start.split(":"))
        e_h, e_m = (int(x) for x in self.end.split(":"))
        s = dtime(s_h, s_m)
        e = dtime(e_h, e_m)
        cur = now.time()
        return s <= cur <= e


@dataclass
class TenantRiskState:
    tenant_id: str
    daily_quota: int = DAILY_QUOTA_NEW
    today_sent: int = 0
    today_date: Optional[str] = None
    schedule: WorkSchedule = field(default_factory=WorkSchedule)


class RiskController:
    def __init__(self):
        self._state: dict[str, TenantRiskState] = {}

    def register(self, tenant_id: str, daily_quota: int = DAILY_QUOTA_NEW, schedule: Optional[WorkSchedule] = None) -> None:
        self._state[tenant_id] = TenantRiskState(
            tenant_id=tenant_id,
            daily_quota=min(daily_quota, DAILY_QUOTA_MAX),
            schedule=schedule or WorkSchedule(),
        )

    def is_workhour(self, tenant_id: str, now: Optional[datetime] = None) -> bool:
        state = self._state.get(tenant_id)
        if not state:
            return True  # 未注册按宽松
        return state.schedule.is_workhour(now)

    def quota_remaining(self, tenant_id: str) -> int:
        state = self._state.get(tenant_id)
        if not state:
            return DAILY_QUOTA_NEW
        self._reset_if_new_day(state)
        return max(0, state.daily_quota - state.today_sent)

    def can_send(self, tenant_id: str, now: Optional[datetime] = None) -> bool:
        if not self.is_workhour(tenant_id, now):
            return False
        return self.quota_remaining(tenant_id) > 0

    def consume(self, tenant_id: str, now: Optional[datetime] = None) -> None:
        """记一次发送。"""
        if not self.is_workhour(tenant_id, now):
            raise WorkhourViolationError(f"tenant {tenant_id} 当前非工作时间")
        if self.quota_remaining(tenant_id) <= 0:
            raise QuotaExceededError(f"tenant {tenant_id} 今日配额耗尽")
        state = self._state[tenant_id]
        state.today_sent += 1

    @staticmethod
    def _reset_if_new_day(state: TenantRiskState) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        if state.today_date != today:
            state.today_date = today
            state.today_sent = 0

    def upgrade_quota(self, tenant_id: str, new_value: int) -> None:
        """养号期 30→100 升级。最高 150。"""
        if tenant_id not in self._state:
            return
        self._state[tenant_id].daily_quota = min(new_value, DAILY_QUOTA_MAX)
