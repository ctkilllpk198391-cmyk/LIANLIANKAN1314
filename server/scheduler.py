"""F6/F4 · APScheduler 集中管理 · 后台 cron jobs。

注册的 jobs：
  - 每 1 分钟 · follow_up.tick     （C1 待集成）
  - 每 5 分钟 · health_monitor.tick_all
  - 每天 02:00 · customer_profile.weekly_compact（待实现 · 占位）
  - 每周一 09:00 · weekly_report.send_all（B4 待集成）

启动：
  在 server/main.py lifespan 启动时 init_scheduler() · 关闭时 shutdown_scheduler()
"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

_scheduler = None


def get_scheduler():
    global _scheduler
    if _scheduler is None:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            _scheduler = AsyncIOScheduler()
        except ImportError:
            logger.warning("apscheduler not installed · scheduler will be no-op")
            _scheduler = _NoopScheduler()
    return _scheduler


def init_scheduler(
    health_tick: Optional[Callable[[], Awaitable[int]]] = None,
    follow_up_tick: Optional[Callable[[], Awaitable[int]]] = None,
    weekly_report: Optional[Callable[[], Awaitable[int]]] = None,
    moments_tick: Optional[Callable[[], Awaitable[int]]] = None,
):
    """注册 jobs 并启动。多次调用幂等。"""
    sch = get_scheduler()
    if isinstance(sch, _NoopScheduler):
        return sch

    if health_tick and not _job_exists(sch, "health_tick"):
        sch.add_job(health_tick, "interval", minutes=5, id="health_tick", replace_existing=True)
    if follow_up_tick and not _job_exists(sch, "follow_up_tick"):
        sch.add_job(follow_up_tick, "interval", minutes=1, id="follow_up_tick", replace_existing=True)
    if weekly_report and not _job_exists(sch, "weekly_report"):
        sch.add_job(weekly_report, "cron", day_of_week="mon", hour=9, id="weekly_report", replace_existing=True)
    # S8 朋友圈托管 · 每小时扫到点的 scheduled posts
    if moments_tick and not _job_exists(sch, "moments_tick"):
        sch.add_job(moments_tick, "interval", hours=1, id="moments_tick", replace_existing=True)

    if not getattr(sch, "running", False):
        sch.start()
        logger.info("scheduler started · jobs=%s", [j.id for j in sch.get_jobs()])
    return sch


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        if not isinstance(_scheduler, _NoopScheduler) and getattr(_scheduler, "running", False):
            _scheduler.shutdown(wait=False)
            logger.info("scheduler shutdown")
    except Exception as e:
        logger.warning("scheduler shutdown error: %s", e)
    _scheduler = None


def _job_exists(sch, job_id: str) -> bool:
    try:
        return sch.get_job(job_id) is not None
    except Exception:
        return False


class _NoopScheduler:
    """apscheduler 缺失时的兜底 · 不报错 · 不调度。"""

    running = False

    def add_job(self, *_args, **_kwargs):
        return None

    def get_jobs(self):
        return []

    def get_job(self, _id):
        return None

    def start(self):
        self.running = True

    def shutdown(self, *_args, **_kwargs):
        self.running = False
