"""周报模块 · 生成 Markdown + 推飞书 webhook（mock 兜底）。"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from server.dashboard import DashboardBuilder

logger = logging.getLogger(__name__)

_REPORT_TEMPLATE = """\
# wechat_agent周报 · {tenant_id}
> 生成时间：{as_of_str}

## 本周数据摘要

| 指标 | 数值 |
|------|------|
| 今日采纳率 | {acceptance_rate:.1%} |
| 今日已发 | {sent} 条 |
| 客户总数 | {customer_total} 人 |
| VIP-A | {tier_a} 人 |
| 活跃-B | {tier_b} 人 |
| 沉睡-C | {stale_count} 人待唤醒 |

## 成交漏斗

| 阶段 | 数量 | 转化率 |
|------|------|--------|
| 询价 | {inq} | — |
| 砍价 | {neg} | {inq_to_neg:.1%} |
| 下单 | {order} | {neg_to_order:.1%} |
| 复购 | {rep} | {order_to_rep:.1%} |

## 同行对标

- **你的采纳率**：{your_rate:.1%}
- **行业均值 (P50)**：{p50:.1%}
- **行业优秀 (P90)**：{p90:.1%}
- **超过均值**：{delta_pct:+.1f}%

## 沉睡客户提醒（top 10 · 30 天未联系）

{stale_list}

---
*由wechat_agent自动生成 · 每周一 09:00 推送*
"""


class WeeklyReportBuilder:
    def __init__(self):
        self._dashboard = DashboardBuilder()

    async def build_markdown(self, tenant_id: str) -> str:
        v2 = await self._dashboard.build_v2(tenant_id)
        now_str = datetime.fromtimestamp(v2["as_of"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        today = v2["today"]
        customers = v2["customers"]
        funnel = v2["funnel"]
        rates = funnel["rates"]
        bench = v2["benchmark"]

        stale = customers.get("stale_30d_alert", [])
        if stale:
            stale_list = "\n".join(f"- {cid}" for cid in stale)
        else:
            stale_list = "（暂无沉睡客户）"

        return _REPORT_TEMPLATE.format(
            tenant_id=tenant_id,
            as_of_str=now_str,
            acceptance_rate=today["acceptance_rate"],
            sent=today["sent"],
            customer_total=customers["total"],
            tier_a=customers["tier_a"],
            tier_b=customers["tier_b"],
            stale_count=len(stale),
            inq=funnel["inquiry"],
            neg=funnel["negotiation"],
            order=funnel["order"],
            rep=funnel["repurchase"],
            inq_to_neg=rates["inq_to_neg"],
            neg_to_order=rates["neg_to_order"],
            order_to_rep=rates["order_to_rep"],
            your_rate=bench["your_acceptance_rate"],
            p50=bench["industry_p50"],
            p90=bench["industry_p90"],
            delta_pct=bench["delta_pct"],
            stale_list=stale_list,
        )


class WeeklyReportSender:
    def __init__(self):
        self._webhook = os.getenv("BAIYANG_FEISHU_WEBHOOK", "")

    async def send(self, tenant_id: str, markdown: str) -> dict:
        if not self._webhook:
            logger.info("[weekly_report] BAIYANG_FEISHU_WEBHOOK not set · print only")
            print(f"=== 周报 ({tenant_id}) ===\n{markdown}")
            return {"ok": True, "mode": "print"}

        try:
            import urllib.request
            import json as _json

            payload = _json.dumps({
                "msg_type": "text",
                "content": {"text": markdown},
            }).encode()
            req = urllib.request.Request(
                self._webhook,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = resp.read().decode()
            logger.info("[weekly_report] feishu sent tenant=%s resp=%s", tenant_id, body)
            return {"ok": True, "mode": "feishu", "resp": body}
        except Exception as exc:
            logger.error("[weekly_report] feishu send failed: %s", exc)
            return {"ok": False, "mode": "feishu", "error": str(exc)}
