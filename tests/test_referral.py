"""referral.py 测试。"""

from __future__ import annotations

import pytest

from server.referral import REFERRAL_REWARD_CENTS, ReferralManager


def test_create_code_idempotent():
    rm = ReferralManager()
    c1 = rm.create_code("tenant_0001")
    c2 = rm.create_code("tenant_0001")
    assert c1 == c2
    assert len(c1) == 6


def test_claim_reward():
    rm = ReferralManager()
    code = rm.create_code("tenant_0001")
    reward = rm.claim_reward(code, "tenant_0002", paid_cents=200000)
    assert reward == REFERRAL_REWARD_CENTS
    stats = rm.stats("tenant_0001")
    assert stats["successful_referrals"] == 1
    assert stats["total_reward_cents"] == REFERRAL_REWARD_CENTS


def test_unknown_code():
    rm = ReferralManager()
    with pytest.raises(ValueError):
        rm.claim_reward("DEADBE", "tenant_x", 0)


def test_double_claim_blocked():
    rm = ReferralManager()
    code = rm.create_code("tenant_0001")
    rm.claim_reward(code, "tenant_0002", paid_cents=200000)
    with pytest.raises(ValueError):
        rm.claim_reward(code, "tenant_0003", paid_cents=200000)


def test_self_referral_blocked():
    rm = ReferralManager()
    code = rm.create_code("tenant_0001")
    with pytest.raises(ValueError):
        rm.claim_reward(code, "tenant_0001", paid_cents=200000)
