"""早鸟定金机制 · ¥199 锁名额 · 30 天内全额抵扣 ¥1980 安装费。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

EARLY_BIRD_DEPOSIT_CENTS = 19900   # ¥199.00
PRO_INSTALL_CENTS = 198000          # ¥1980.00
PRO_MONTHLY_CENTS = 69900           # ¥699.00（专业版月费 · landing 早鸟优惠 ¥299）
EARLY_BIRD_MONTHLY_DISCOUNT_CENTS = 29900  # ¥299
SLOTS_TOTAL = 10
TRIAL_DAYS = 30
REFUND_DAYS = 7


@dataclass
class EarlyBirdSlot:
    slot_no: int
    contact_info: dict
    paid_deposit: int = 0
    reserved_at: int = 0
    converted: bool = False
    refunded: bool = False
    expires_at: int = 0


class EarlyBirdManager:
    """前 10 名 ¥199 定金 · 30 天后转正抵扣全部安装费。"""

    def __init__(self):
        self._slots: dict[int, EarlyBirdSlot] = {}
        self._next = 1

    def remaining_slots(self) -> int:
        active = sum(1 for s in self._slots.values() if not s.refunded)
        return max(0, SLOTS_TOTAL - active)

    def reserve_slot(self, contact_info: dict, paid_amount_cents: int) -> EarlyBirdSlot:
        if paid_amount_cents != EARLY_BIRD_DEPOSIT_CENTS:
            raise ValueError(f"定金应为 {EARLY_BIRD_DEPOSIT_CENTS} 分")
        if self.remaining_slots() <= 0:
            raise ValueError("早鸟名额已满 · 等下一批")

        slot_no = self._next
        self._next += 1
        now = int(time.time())
        slot = EarlyBirdSlot(
            slot_no=slot_no,
            contact_info=contact_info,
            paid_deposit=paid_amount_cents,
            reserved_at=now,
            expires_at=now + TRIAL_DAYS * 86400,
        )
        self._slots[slot_no] = slot
        logger.info("early bird slot #%d reserved · expires_at=%d", slot_no, slot.expires_at)
        return slot

    def calculate_convert_payment(self, slot_no: int) -> dict:
        """转正需要补：(¥1980 - ¥199 定金) + 首月 ¥299（早鸟价）"""
        slot = self._slots.get(slot_no)
        if not slot:
            raise ValueError(f"slot {slot_no} not found")
        install_due = PRO_INSTALL_CENTS - slot.paid_deposit
        first_month = EARLY_BIRD_MONTHLY_DISCOUNT_CENTS
        return {
            "install_due_cents": install_due,
            "first_month_cents": first_month,
            "total_cents": install_due + first_month,
        }

    def convert(self, slot_no: int, paid_amount_cents: int) -> EarlyBirdSlot:
        slot = self._slots.get(slot_no)
        if not slot:
            raise ValueError(f"slot {slot_no} not found")
        expected = self.calculate_convert_payment(slot_no)["total_cents"]
        if paid_amount_cents != expected:
            raise ValueError(f"金额应为 {expected} 分（含安装+首月）")
        if int(time.time()) > slot.expires_at:
            raise ValueError("早鸟试用期已过 · 不享早鸟价")
        slot.converted = True
        return slot

    def refund(self, slot_no: int) -> EarlyBirdSlot:
        slot = self._slots.get(slot_no)
        if not slot:
            raise ValueError(f"slot {slot_no} not found")
        days_passed = (int(time.time()) - slot.reserved_at) / 86400
        if days_passed > REFUND_DAYS:
            raise ValueError(f"超过 {REFUND_DAYS} 天无理由退款期")
        slot.refunded = True
        return slot
