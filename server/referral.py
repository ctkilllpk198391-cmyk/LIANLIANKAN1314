"""转介绍机制 · 邀请码 + 现金返还。"""

from __future__ import annotations

import logging
import secrets
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

REFERRAL_REWARD_CENTS = 20000  # ¥200


@dataclass
class ReferralRecord:
    code: str
    referrer_tenant: str
    new_tenant: str | None = None
    new_tenant_paid_cents: int = 0
    reward_cents: int = 0
    rewarded_at: int = 0


class ReferralManager:
    def __init__(self):
        self._codes: dict[str, ReferralRecord] = {}
        self._tenant_codes: dict[str, str] = {}

    def create_code(self, referrer_tenant: str) -> str:
        if referrer_tenant in self._tenant_codes:
            return self._tenant_codes[referrer_tenant]
        code = secrets.token_hex(3).upper()
        self._codes[code] = ReferralRecord(code=code, referrer_tenant=referrer_tenant)
        self._tenant_codes[referrer_tenant] = code
        return code

    def claim_reward(self, code: str, new_tenant: str, paid_cents: int) -> int:
        rec = self._codes.get(code)
        if not rec:
            raise ValueError(f"unknown referral code: {code}")
        if rec.new_tenant:
            raise ValueError(f"code {code} already claimed by {rec.new_tenant}")
        if new_tenant == rec.referrer_tenant:
            raise ValueError("不能给自己返现")
        rec.new_tenant = new_tenant
        rec.new_tenant_paid_cents = paid_cents
        rec.reward_cents = REFERRAL_REWARD_CENTS
        rec.rewarded_at = int(time.time())
        logger.info(
            "referral reward · referrer=%s new=%s paid=%d reward=%d",
            rec.referrer_tenant, new_tenant, paid_cents, rec.reward_cents,
        )
        return rec.reward_cents

    def stats(self, referrer_tenant: str) -> dict:
        records = [r for r in self._codes.values() if r.referrer_tenant == referrer_tenant]
        return {
            "code": self._tenant_codes.get(referrer_tenant),
            "successful_referrals": sum(1 for r in records if r.new_tenant),
            "total_reward_cents": sum(r.reward_cents for r in records),
        }
