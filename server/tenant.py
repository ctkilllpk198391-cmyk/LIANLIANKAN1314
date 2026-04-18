"""TenantManager · tenant 加载、查询、跨 tenant 隔离强制。"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import select

from server.db import session_scope
from server.models import Tenant
from shared.errors import CrossTenantError, TenantNotFoundError
from shared.proto import TenantConfig


class TenantManager:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self._cache: dict[str, TenantConfig] = {}

    def load_from_yaml(self) -> int:
        """从 tenants.yaml 加载所有 tenant 到 cache。返回数量。"""
        if not self.config_path or not self.config_path.exists():
            return 0
        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}
        count = 0
        for entry in data.get("tenants", []):
            tc = TenantConfig(
                tenant_id=entry["tenant_id"],
                boss_name=entry["boss_name"],
                plan=entry.get("plan", "trial"),
                daily_quota=entry.get("daily_quota", 30),
                style_hints=entry.get("style_hints", ""),
            )
            self._cache[tc.tenant_id] = tc
            count += 1
        return count

    def get(self, tenant_id: str) -> TenantConfig:
        if tenant_id not in self._cache:
            raise TenantNotFoundError(f"tenant {tenant_id} not loaded")
        return self._cache[tenant_id]

    def has(self, tenant_id: str) -> bool:
        return tenant_id in self._cache

    @staticmethod
    def enforce_isolation(request_tenant: str, resource_tenant: str) -> None:
        """跨 tenant 访问 = 红线 · 立即抛错。"""
        if request_tenant != resource_tenant:
            raise CrossTenantError(
                f"isolation violated: request={request_tenant} resource={resource_tenant}"
            )

    async def upsert_to_db(self, tc: TenantConfig) -> None:
        async with session_scope() as session:
            existing = (
                await session.execute(select(Tenant).where(Tenant.tenant_id == tc.tenant_id))
            ).scalar_one_or_none()
            payload_json = json.dumps(tc.model_dump(), ensure_ascii=False)
            if existing:
                existing.boss_name = tc.boss_name
                existing.plan = tc.plan
                existing.config_json = payload_json
            else:
                session.add(
                    Tenant(
                        tenant_id=tc.tenant_id,
                        boss_name=tc.boss_name,
                        plan=tc.plan,
                        created_at=int(time.time()),
                        config_json=payload_json,
                    )
                )

    def list_all(self) -> list[TenantConfig]:
        return list(self._cache.values())
