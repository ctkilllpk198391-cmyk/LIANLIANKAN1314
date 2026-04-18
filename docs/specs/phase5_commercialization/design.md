# Phase 5 · 商业化 · Design

---

## 1. 微信支付集成

```python
# server/billing.py · 简化伪代码
from wechatpayv3 import WeChatPay, WeChatPayType

class BillingManager:
    def __init__(self, mch_id: str, api_v3_key: str, cert_path: Path):
        self.client = WeChatPay(
            wechatpay_type=WeChatPayType.NATIVE,
            mchid=mch_id,
            apiv3_key=api_v3_key,
            ...
        )

    async def create_order(self, tenant_id: str, plan: str, amount_cents: int) -> dict:
        out_trade_no = f"baiyang_{tenant_id}_{int(time.time())}"
        code, message = self.client.pay(
            description=f"白羊订阅 · {plan}",
            out_trade_no=out_trade_no,
            amount={"total": amount_cents},
            notify_url="https://api.baiyang.example/v1/billing/wechatpay_callback",
        )
        return {"out_trade_no": out_trade_no, "code_url": message["code_url"]}

    async def handle_callback(self, raw_body: bytes, headers: dict) -> bool:
        # 验签 + 解密 + 激活订阅
        ...
```

---

## 2. 订阅模型

```python
# server/models.py 增加
class Subscription(Base):
    __tablename__ = "subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=False)
    plan = Column(String(32), nullable=False)        # trial/pro/flagship
    status = Column(String(32), nullable=False)      # active/expired/cancelled
    started_at = Column(Integer, nullable=False)
    expires_at = Column(Integer, nullable=False)
    last_payment_id = Column(String(128))
```

```python
# server/subscription.py
class SubscriptionService:
    async def activate(self, tenant_id: str, plan: str, months: int = 1):
        ...
    async def is_active(self, tenant_id: str) -> bool:
        ...
    async def expiring_soon(self, days: int = 7) -> list[str]:
        ...
```

---

## 3. Dashboard

```python
# server/dashboard.py
class DashboardBuilder:
    async def build(self, tenant_id: str) -> dict:
        async with session_scope() as s:
            today_start = int(time.time()) // 86400 * 86400
            # 今日 suggestions + reviews 聚合
            sugs = (await s.execute(
                select(Suggestion).where(Suggestion.tenant_id == tenant_id)
                .where(Suggestion.generated_at >= today_start)
            )).scalars().all()
            reviews = (await s.execute(
                select(Review).join(Suggestion, Review.msg_id == Suggestion.msg_id)
                .where(Suggestion.tenant_id == tenant_id)
                .where(Review.reviewed_at >= today_start)
            )).scalars().all()

        n_total = len(sugs)
        n_acc = sum(1 for r in reviews if r.decision == "accept")
        n_edit = sum(1 for r in reviews if r.decision == "edit")
        n_rej = sum(1 for r in reviews if r.decision == "reject")
        acceptance = n_acc / max(1, len(reviews))

        return {
            "tenant_id": tenant_id,
            "today": {
                "total_generated": n_total,
                "accepted": n_acc,
                "edited": n_edit,
                "rejected": n_rej,
                "acceptance_rate": round(acceptance, 3),
            },
            "lora_status": {"loaded": True, "version": "v1.2"},
            "quota": {"daily_used": n_total, "daily_max": 100},
        }
```

---

## 4. HTML 简版 Dashboard

```html
<!-- server/templates/dashboard.html -->
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>白羊看板 · {{ tenant_id }}</title>
  <style>
    body { font-family: -apple-system, sans-serif; padding: 20px; max-width: 800px; margin: auto; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
    .metric { font-size: 32px; font-weight: 600; }
    .label { color: #888; font-size: 14px; }
  </style>
</head>
<body>
  <h1>{{ tenant_id }} · 今日数据</h1>
  <div class="card">
    <div class="metric">{{ today.acceptance_rate * 100 | round(1) }}%</div>
    <div class="label">老板采纳率</div>
  </div>
  <div class="card">
    <div class="metric">{{ today.accepted }} / {{ today.total_generated }}</div>
    <div class="label">采纳 / 生成</div>
  </div>
</body>
</html>
```
