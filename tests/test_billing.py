"""billing.py 测试。"""

from __future__ import annotations

import json

import pytest

from server.billing import PLAN_PRICES, BillingManager


def test_create_order_pro_install():
    bm = BillingManager(mock=True)
    o = bm.create_order("tenant_0001", "pro", "install")
    assert o.amount_cents == PLAN_PRICES["pro"]["install"]
    assert o.code_url.startswith("weixin://mock/qr/")
    assert o.status == "pending"


def test_create_order_pro_monthly():
    bm = BillingManager(mock=True)
    o = bm.create_order("tenant_0001", "pro", "monthly")
    assert o.amount_cents == PLAN_PRICES["pro"]["monthly"]


def test_create_order_unknown_plan():
    bm = BillingManager(mock=True)
    with pytest.raises(ValueError):
        bm.create_order("tenant_0001", "alien_plan", "monthly")


def test_create_order_trial_zero_amount_raises():
    bm = BillingManager(mock=True)
    with pytest.raises(ValueError):
        bm.create_order("tenant_0001", "trial", "monthly")


def test_callback_marks_paid():
    bm = BillingManager(mock=True)
    o = bm.create_order("tenant_0001", "pro", "install")
    callback = json.dumps({"out_trade_no": o.out_trade_no}).encode("utf-8")
    res = bm.handle_callback(callback, headers={})
    assert res["code"] == "SUCCESS"
    assert bm.get_order(o.out_trade_no).status == "paid"


def test_callback_unknown_order():
    bm = BillingManager(mock=True)
    cb = json.dumps({"out_trade_no": "doesnt_exist"}).encode()
    res = bm.handle_callback(cb, headers={})
    assert res["code"] == "ORDER_NOT_FOUND"
