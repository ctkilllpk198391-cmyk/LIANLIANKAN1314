"""F6 · 24/7 反封号引擎 · 5 维度健康监控 · 自动调速/暂停。

5 维度：
  friend_pass_rate    好友通过率
  msg_similarity_avg  消息相似度均值
  reply_rate          客户回复率
  ip_switches         IP 切换次数
  heartbeat_anomaly   心跳异常次数

评分：
  composite = Σ weight_i * score_i / 100
  score 0-100 · 越高越健康

自动响应：
  green  ≥80   正常
  yellow 60-80 quota 砍半 · 单聊间隔 ×2
  red    <60   暂停 1 小时 · 触发 F7 容灾切号

集成：
  - on_record(metric_name, value): 客户端/server 调 · 写指标
  - tick_all(): APScheduler 每 5 分钟跑 · 全 tenant 评估 · 红灯回调
  - on_red_callback: 用于 F7 account_failover 钩子
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import AccountHealthMetric, AccountHealthStatus

logger = logging.getLogger(__name__)


WEIGHTS = {
    "friend_pass_rate":   25,
    "msg_similarity_avg": 25,
    "reply_rate":         20,
    "ip_switches":        15,
    "heartbeat_anomaly":  15,
}


def score_metric(name: str, value: float) -> float:
    """单维度评分 0-100。"""
    if name == "friend_pass_rate":
        return min(100.0, max(0.0, value / 0.85 * 100))
    if name == "msg_similarity_avg":
        return min(100.0, max(0.0, (1 - value / 0.6) * 100))
    if name == "reply_rate":
        return min(100.0, max(0.0, value / 0.4 * 100))
    if name == "ip_switches":
        return max(0.0, 100 - value * 20)
    if name == "heartbeat_anomaly":
        return max(0.0, 100 - value * 25)
    return 50.0


def composite_score(metrics: dict[str, float]) -> float:
    """加权综合分 · 缺失维度按 50 分中性处理 · 仅按 metric 提供的维度计算。"""
    if not metrics:
        return 100.0  # 无数据 = 假定健康
    total_weight = 0
    weighted_sum = 0.0
    for name, weight in WEIGHTS.items():
        if name in metrics:
            score = score_metric(name, metrics[name])
            weighted_sum += weight * score
            total_weight += weight
    if total_weight == 0:
        return 100.0
    # normalize to 0-100 against actual provided weights
    raw = weighted_sum / total_weight
    return round(raw, 1)


def health_level(score: float) -> str:
    if score >= 80:
        return "green"
    if score >= 60:
        return "yellow"
    return "red"


def quota_for_level(level: str, base_quota: int) -> int:
    if level == "green":
        return base_quota
    if level == "yellow":
        return max(1, base_quota // 2)
    return 0  # red 暂停


@dataclass
class HealthSnapshot:
    tenant_id: str
    account_id: str
    score: float
    level: str
    metrics: dict[str, float]
    last_evaluated_at: int
    paused_until: Optional[int] = None
    daily_quota_override: Optional[int] = None


RedCallback = Callable[[str, str, HealthSnapshot], Awaitable[None]]   # (tenant_id, account_id, snapshot)


class HealthMonitor:
    """5 维度健康监控核心。"""

    METRIC_WINDOW_SEC = 3600  # 评估时只取最近 1 小时的指标

    def __init__(self, on_red: Optional[RedCallback] = None, base_quota: int = 100):
        self.on_red = on_red
        self.base_quota = base_quota
        self._tenants_to_watch: set[tuple[str, str]] = set()  # (tenant_id, account_id)

    def watch(self, tenant_id: str, account_id: str = "primary") -> None:
        self._tenants_to_watch.add((tenant_id, account_id))

    def unwatch(self, tenant_id: str, account_id: str = "primary") -> None:
        self._tenants_to_watch.discard((tenant_id, account_id))

    def list_watched(self) -> list[tuple[str, str]]:
        return list(self._tenants_to_watch)

    async def record(
        self,
        tenant_id: str,
        account_id: str,
        metric_name: str,
        value: float,
    ) -> None:
        async with session_scope() as session:
            session.add(
                AccountHealthMetric(
                    tenant_id=tenant_id,
                    account_id=account_id,
                    metric_name=metric_name,
                    value=value,
                    recorded_at=int(time.time()),
                )
            )
        self.watch(tenant_id, account_id)

    async def evaluate(self, tenant_id: str, account_id: str) -> HealthSnapshot:
        cutoff = int(time.time()) - self.METRIC_WINDOW_SEC
        async with session_scope() as session:
            rows = (
                await session.execute(
                    select(AccountHealthMetric)
                    .where(AccountHealthMetric.tenant_id == tenant_id)
                    .where(AccountHealthMetric.account_id == account_id)
                    .where(AccountHealthMetric.recorded_at >= cutoff)
                    .order_by(AccountHealthMetric.recorded_at.desc())
                )
            ).scalars().all()

        # 取每个 metric 最新值
        latest: dict[str, float] = {}
        for r in rows:
            if r.metric_name not in latest:
                latest[r.metric_name] = r.value

        score = composite_score(latest)
        level = health_level(score)
        now = int(time.time())
        paused_until = None
        quota_override: Optional[int] = None

        if level == "red":
            paused_until = now + 3600
            quota_override = 0
        elif level == "yellow":
            quota_override = max(1, self.base_quota // 2)

        # upsert status
        async with session_scope() as session:
            existing = (
                await session.execute(
                    select(AccountHealthStatus)
                    .where(AccountHealthStatus.tenant_id == tenant_id)
                    .where(AccountHealthStatus.account_id == account_id)
                )
            ).scalar_one_or_none()

            if existing:
                existing.score = score
                existing.level = level
                existing.daily_quota_override = quota_override
                existing.paused_until = paused_until
                existing.last_evaluated_at = now
            else:
                session.add(
                    AccountHealthStatus(
                        tenant_id=tenant_id,
                        account_id=account_id,
                        score=score,
                        level=level,
                        daily_quota_override=quota_override,
                        paused_until=paused_until,
                        last_evaluated_at=now,
                    )
                )

        snap = HealthSnapshot(
            tenant_id=tenant_id,
            account_id=account_id,
            score=score,
            level=level,
            metrics=latest,
            last_evaluated_at=now,
            paused_until=paused_until,
            daily_quota_override=quota_override,
        )

        if level == "red" and self.on_red is not None:
            try:
                await self.on_red(tenant_id, account_id, snap)
            except Exception as e:
                logger.error("on_red callback failed: %s", e)

        return snap

    async def get_status(self, tenant_id: str, account_id: str) -> Optional[HealthSnapshot]:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(AccountHealthStatus)
                    .where(AccountHealthStatus.tenant_id == tenant_id)
                    .where(AccountHealthStatus.account_id == account_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return None
            return HealthSnapshot(
                tenant_id=tenant_id,
                account_id=account_id,
                score=row.score,
                level=row.level,
                metrics={},
                last_evaluated_at=row.last_evaluated_at,
                paused_until=row.paused_until,
                daily_quota_override=row.daily_quota_override,
            )

    async def manual_recover(self, tenant_id: str, account_id: str) -> bool:
        async with session_scope() as session:
            row = (
                await session.execute(
                    select(AccountHealthStatus)
                    .where(AccountHealthStatus.tenant_id == tenant_id)
                    .where(AccountHealthStatus.account_id == account_id)
                )
            ).scalar_one_or_none()
            if row is None:
                return False
            row.score = 80.0
            row.level = "green"
            row.daily_quota_override = None
            row.paused_until = None
            row.last_evaluated_at = int(time.time())
        return True

    async def tick_all(self) -> int:
        """APScheduler 每 5 分钟调 · 评估所有 watched tenant/account。"""
        n = 0
        for tenant_id, account_id in list(self._tenants_to_watch):
            try:
                await self.evaluate(tenant_id, account_id)
                n += 1
            except Exception as e:
                logger.error("evaluate failed tenant=%s account=%s: %s", tenant_id, account_id, e)
        return n
