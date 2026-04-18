"""C2 · 训练队列测试（替代 industry_flywheel · 删除论文级飞轮设计）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from evolution.training_queue import TrainingQueueEngine, WEIGHTS
from shared.proto import IntentResult, ReviewDecision, Suggestion
from shared.types import EmotionEnum, IntentEnum, ReviewDecisionEnum, RiskEnum


def _mk_sug(text="您好亲~", intent=IntentEnum.GREETING):
    return Suggestion(
        msg_id="sug_001",
        tenant_id="tenant_0001",
        inbound_msg_id="in_001",
        intent=IntentResult(intent=intent, emotion=EmotionEnum.CALM, risk=RiskEnum.LOW, confidence=0.8),
        text=text,
        model_route="mock",
        generated_at=int(time.time()),
    )


def _mk_decision(decision=ReviewDecisionEnum.ACCEPT, edited=None):
    return ReviewDecision(
        msg_id="sug_001",
        decision=decision,
        edited_text=edited,
        reviewed_at=int(time.time()),
    )


@pytest.mark.asyncio
async def test_append_accept_weight_1(temp_db):
    eng = TrainingQueueEngine()
    sug = _mk_sug()
    decision = _mk_decision(ReviewDecisionEnum.ACCEPT)
    row_id = await eng.append("tenant_0001", "你好 在吗", sug, decision)
    assert row_id > 0

    stats = await eng.stats("tenant_0001")
    assert stats["total_samples"] == 1
    assert stats["by_decision"]["accept"] == 1
    assert stats["total_weight"] == 1.0


@pytest.mark.asyncio
async def test_append_edit_uses_edited_text(temp_db):
    eng = TrainingQueueEngine()
    sug = _mk_sug(text="原始 AI 回复")
    decision = _mk_decision(ReviewDecisionEnum.EDIT, edited="老板修改后")
    await eng.append("tenant_0001", "客户问", sug, decision)

    output = Path("/tmp/baiyang_test_export.jsonl")
    n = await eng.export("tenant_0001", output)
    assert n == 1
    line = json.loads(output.read_text().strip())
    assert line["output"] == "老板修改后"
    assert abs(line["weight"] - 0.7) < 1e-6
    output.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_append_reject_negative_weight(temp_db):
    eng = TrainingQueueEngine()
    sug = _mk_sug()
    decision = _mk_decision(ReviewDecisionEnum.REJECT)
    await eng.append("tenant_0001", "客户问", sug, decision)
    stats = await eng.stats("tenant_0001")
    assert stats["total_weight"] == -0.5


@pytest.mark.asyncio
async def test_append_auto_sent_weight_0_5(temp_db):
    eng = TrainingQueueEngine()
    await eng.append_auto_sent("tenant_0001", "你好", _mk_sug())
    stats = await eng.stats("tenant_0001")
    assert stats["by_decision"]["auto_sent"] == 1
    assert stats["total_weight"] == 0.5


@pytest.mark.asyncio
async def test_export_min_weight_filters(temp_db):
    eng = TrainingQueueEngine()
    await eng.append("t1", "msg", _mk_sug(), _mk_decision(ReviewDecisionEnum.ACCEPT))   # 1.0
    await eng.append("t1", "msg", _mk_sug(), _mk_decision(ReviewDecisionEnum.REJECT))   # -0.5

    output = Path("/tmp/baiyang_test_export2.jsonl")
    n = await eng.export("t1", output, min_weight=0.5)
    assert n == 1
    output.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_tenant_isolation(temp_db):
    eng = TrainingQueueEngine()
    await eng.append("tenant_A", "msg", _mk_sug(), _mk_decision(ReviewDecisionEnum.ACCEPT))
    await eng.append("tenant_B", "msg", _mk_sug(), _mk_decision(ReviewDecisionEnum.ACCEPT))
    sa = await eng.stats("tenant_A")
    sb = await eng.stats("tenant_B")
    assert sa["total_samples"] == 1
    assert sb["total_samples"] == 1


def test_weights_config():
    """硬编码 weights 不被改动。"""
    assert WEIGHTS[ReviewDecisionEnum.ACCEPT] == 1.0
    assert WEIGHTS[ReviewDecisionEnum.EDIT] == 0.7
    assert WEIGHTS[ReviewDecisionEnum.REJECT] == -0.5
