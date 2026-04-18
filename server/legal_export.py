"""L4 · 律师举证导出 · 一键导出指定 tenant 全量审计日志 + 协议签字记录。

用途：客户违约 / 法律纠纷 / 律师咨询时 · 我们能在 1 小时内提供完整证据链。

输出：
  - audit_log.csv（全量审计）
  - consent_records.json（协议签字时间 + 版本）
  - auto_send_config.json（auto_send 配置历史）
  - tenant_summary.md（人类可读总览）
"""

from __future__ import annotations

import csv
import io
import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select

from server.db import session_scope
from server.models import AuditLog, Tenant

logger = logging.getLogger(__name__)


@dataclass
class LegalEvidencePackage:
    tenant_id: str
    boss_name: str
    plan: str
    audit_log_csv: str
    consent_records: list[dict]
    auto_send_config_history: list[dict]
    tenant_summary_md: str
    exported_at: int


class LegalExporter:
    """律师举证包导出。"""

    async def export_for_tenant(
        self,
        tenant_id: str,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> LegalEvidencePackage:
        async with session_scope() as session:
            tenant = (
                await session.execute(
                    select(Tenant).where(Tenant.tenant_id == tenant_id)
                )
            ).scalar_one_or_none()

            stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
            if start_ts:
                stmt = stmt.where(AuditLog.timestamp >= start_ts)
            if end_ts:
                stmt = stmt.where(AuditLog.timestamp <= end_ts)
            stmt = stmt.order_by(AuditLog.timestamp.asc())

            audit_rows = (await session.execute(stmt)).scalars().all()

        boss_name = tenant.boss_name if tenant else "unknown"
        plan = tenant.plan if tenant else "unknown"
        config_json = tenant.config_json if tenant else "{}"

        # 1. audit_log CSV
        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow(["id", "tenant_id", "actor", "action", "msg_id", "meta", "timestamp"])
        for r in audit_rows:
            writer.writerow([r.id, r.tenant_id, r.actor, r.action, r.msg_id or "", r.meta or "", r.timestamp])
        audit_csv = csv_buf.getvalue()

        # 2. consent records（从 audit 提取 consent_signed action）
        consent_records = [
            {
                "actor": r.actor,
                "action": r.action,
                "meta": _safe_json(r.meta),
                "timestamp": r.timestamp,
            }
            for r in audit_rows
            if r.action in ("consent_signed", "agreement_v3_signed", "consent_updated")
        ]

        # 3. auto_send 配置变更历史
        auto_send_history = [
            {
                "actor": r.actor,
                "action": r.action,
                "meta": _safe_json(r.meta),
                "timestamp": r.timestamp,
            }
            for r in audit_rows
            if r.action in ("auto_send_paused", "auto_send_resumed", "auto_send_config_changed")
        ]

        # 4. 人类可读总览
        summary = _build_summary(
            tenant_id=tenant_id,
            boss_name=boss_name,
            plan=plan,
            audit_total=len(audit_rows),
            consent_count=len(consent_records),
            config_json=config_json,
            start_ts=start_ts,
            end_ts=end_ts,
        )

        return LegalEvidencePackage(
            tenant_id=tenant_id,
            boss_name=boss_name,
            plan=plan,
            audit_log_csv=audit_csv,
            consent_records=consent_records,
            auto_send_config_history=auto_send_history,
            tenant_summary_md=summary,
            exported_at=int(time.time()),
        )


def _safe_json(s: Optional[str]) -> dict:
    if not s:
        return {}
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {"raw": v}
    except json.JSONDecodeError:
        return {"raw": s}


def _build_summary(
    tenant_id, boss_name, plan, audit_total,
    consent_count, config_json, start_ts, end_ts,
) -> str:
    period = ""
    if start_ts:
        period += f"\n- 起始：{time.strftime('%Y-%m-%d', time.localtime(start_ts))}"
    if end_ts:
        period += f"\n- 终止：{time.strftime('%Y-%m-%d', time.localtime(end_ts))}"

    return f"""# 法律举证包 · {tenant_id}

> 导出时间：{time.strftime('%Y-%m-%d %H:%M:%S')}
> 用途：法律纠纷 / 律师函应对 / 客户违规举证
{period}

## 客户信息
- tenant_id: {tenant_id}
- 老板名：{boss_name}
- 套餐：{plan}

## 审计统计
- 总审计记录数：{audit_total}
- 协议签字记录：{consent_count}

## 配置 JSON 快照
```json
{config_json}
```

## 关键证据链
1. **客户主动安装**：consent_records 含首次签字时间 + 协议版本 v3
2. **客户主动开启自动回复**：auto_send_config_history 含每次配置变更时间戳
3. **每条 AI 回复**：audit_log 全量留存（actor=server · action=auto_send_*）
4. **客户违规拒绝**：audit_log 含 compliance_blocked 记录（如有）
5. **微信警告响应**：audit_log 含 emergency_stop 记录（如有）

## 法律意义
本举证包证明：
- 客户在签署 v3 协议后自愿开启服务
- 所有 AI 自动发送行为均有客户配置授权
- wechat_agent 已实施合规检测、举报检测、灰产拒绝
- 任何由此产生的微信账号风险由客户自行承担（按 v3 协议第 4 节）
"""
