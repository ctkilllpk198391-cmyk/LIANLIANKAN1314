"""微信支付 + 订阅生命周期 · Phase 5 骨架。"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Literal, Optional

logger = logging.getLogger(__name__)

PLAN_PRICES = {
    "trial": {"install": 0, "monthly": 0},
    "pro": {"install": 198000, "monthly": 69900},          # 单位：分
    "flagship": {"install": 498000, "monthly": 199900},
}


@dataclass
class Order:
    out_trade_no: str
    tenant_id: str
    plan: str
    amount_cents: int
    description: str
    created_at: int
    code_url: Optional[str] = None
    status: Literal["pending", "paid", "refunded", "cancelled"] = "pending"


class BillingManager:
    """微信支付商户接入 + 订单管理。

    Phase 5 真正接入需要 mch_id / api_v3_key / cert · 这里先 mock。
    """

    def __init__(
        self,
        mch_id: Optional[str] = None,
        api_v3_key: Optional[str] = None,
        notify_url: str = "https://api.baiyang.example/v1/billing/wechatpay_callback",
        mock: bool = True,
    ):
        self.mch_id = mch_id
        self.api_v3_key = api_v3_key
        self.notify_url = notify_url
        self.mock = mock or not (mch_id and api_v3_key)
        self._orders: dict[str, Order] = {}

    def create_order(
        self,
        tenant_id: str,
        plan: str,
        billing_type: Literal["install", "monthly"] = "monthly",
    ) -> Order:
        if plan not in PLAN_PRICES:
            raise ValueError(f"unknown plan: {plan}")
        amount = PLAN_PRICES[plan][billing_type]
        if amount == 0:
            raise ValueError(f"plan {plan} {billing_type} 免费 · 不需创建订单")

        out_trade_no = f"baiyang_{tenant_id}_{billing_type}_{uuid.uuid4().hex[:12]}"
        order = Order(
            out_trade_no=out_trade_no,
            tenant_id=tenant_id,
            plan=plan,
            amount_cents=amount,
            description=f"wechat_agent 订阅 · {plan} · {billing_type}",
            created_at=int(time.time()),
        )
        if self.mock:
            order.code_url = f"weixin://mock/qr/{out_trade_no}"
        else:
            order.code_url = self._real_create(order)
        self._orders[out_trade_no] = order
        return order

    def _real_create(self, order: Order) -> str:
        # Phase 5 真集成：from wechatpayv3 import WeChatPay; ...
        raise NotImplementedError("real wechatpay 等 Phase 5 配齐 mch_id")

    def handle_callback(self, raw_body: bytes, headers: dict) -> dict:
        """微信支付异步回调 · 验签 + 解密 + 标记订单。

        Phase 5 真实现：用 wechatpayv3 验 Wechatpay-Serial / Wechatpay-Signature
        Phase 1 mock：直接信任 raw_body 中的 out_trade_no。
        """
        if self.mock:
            import json
            try:
                payload = json.loads(raw_body.decode("utf-8"))
                otn = payload["out_trade_no"]
            except Exception as e:
                return {"code": "PARSE_ERROR", "message": str(e)}
            order = self._orders.get(otn)
            if not order:
                return {"code": "ORDER_NOT_FOUND"}
            order.status = "paid"
            return {"code": "SUCCESS", "out_trade_no": otn, "tenant_id": order.tenant_id}
        raise NotImplementedError

    def get_order(self, out_trade_no: str) -> Optional[Order]:
        return self._orders.get(out_trade_no)
