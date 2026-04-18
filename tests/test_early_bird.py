"""early_bird.py 测试。"""

from __future__ import annotations

import time

import pytest

from server.early_bird import (
    EARLY_BIRD_DEPOSIT_CENTS,
    EARLY_BIRD_MONTHLY_DISCOUNT_CENTS,
    PRO_INSTALL_CENTS,
    SLOTS_TOTAL,
    EarlyBirdManager,
)


def test_initial_slots():
    eb = EarlyBirdManager()
    assert eb.remaining_slots() == SLOTS_TOTAL


def test_reserve_one_slot():
    eb = EarlyBirdManager()
    s = eb.reserve_slot({"name": "测试客户"}, EARLY_BIRD_DEPOSIT_CENTS)
    assert s.slot_no == 1
    assert s.paid_deposit == EARLY_BIRD_DEPOSIT_CENTS
    assert eb.remaining_slots() == SLOTS_TOTAL - 1


def test_reserve_wrong_amount():
    eb = EarlyBirdManager()
    with pytest.raises(ValueError):
        eb.reserve_slot({"name": "x"}, 10000)


def test_reserve_full():
    eb = EarlyBirdManager()
    for i in range(SLOTS_TOTAL):
        eb.reserve_slot({"name": f"c{i}"}, EARLY_BIRD_DEPOSIT_CENTS)
    with pytest.raises(ValueError):
        eb.reserve_slot({"name": "overflow"}, EARLY_BIRD_DEPOSIT_CENTS)


def test_calculate_convert_payment():
    eb = EarlyBirdManager()
    s = eb.reserve_slot({"name": "x"}, EARLY_BIRD_DEPOSIT_CENTS)
    quote = eb.calculate_convert_payment(s.slot_no)
    expected = (PRO_INSTALL_CENTS - EARLY_BIRD_DEPOSIT_CENTS) + EARLY_BIRD_MONTHLY_DISCOUNT_CENTS
    assert quote["total_cents"] == expected


def test_convert():
    eb = EarlyBirdManager()
    s = eb.reserve_slot({"name": "x"}, EARLY_BIRD_DEPOSIT_CENTS)
    quote = eb.calculate_convert_payment(s.slot_no)
    converted = eb.convert(s.slot_no, quote["total_cents"])
    assert converted.converted is True


def test_refund_within_window():
    eb = EarlyBirdManager()
    s = eb.reserve_slot({"name": "x"}, EARLY_BIRD_DEPOSIT_CENTS)
    refunded = eb.refund(s.slot_no)
    assert refunded.refunded is True
    assert eb.remaining_slots() == SLOTS_TOTAL  # 退款释放名额
