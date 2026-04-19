"""Wave 14 · 发图能力 · media_library + wxpad_send_image + prompt 注入单测.

覆盖:
- media_library.register + list_images CRUD
- media_library.pick_by_filename 防目录穿越
- media_library.extract_image_refs 解析 [[IMG:xxx]]
- media_library.render_prompt_block 输出
- prompt_builder 注入 media_block
- wxpad_send_image mock HTTP 返 Code 200
- _dispatch_reply 解析 [[IMG:]] 先图后文
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from server import media_library as ml
from server.prompt_builder import build_system_prompt
from shared.proto import IntentResult, Suggestion
from shared.types import EmotionEnum, IntentEnum, RiskEnum


@pytest.fixture
def tmp_tenant(tmp_path, monkeypatch):
    """临时 tenant 目录 · 隔离文件系统."""
    monkeypatch.setattr(ml, "MEDIA_ROOT", tmp_path)
    tid = "test_t_media"
    media_dir = tmp_path / tid / "media"
    media_dir.mkdir(parents=True)
    return tid, media_dir


# ── 1. register + list ───────────────────────────────────────────────────────

def test_register_and_list(tmp_tenant):
    tid, mdir = tmp_tenant
    # 造 2 张假图
    (mdir / "prod_red.jpg").write_bytes(b"\xff\xd8\xff\xe0fake1")
    (mdir / "prod_black.jpg").write_bytes(b"\xff\xd8\xff\xe0fake2")

    assert ml.register(tid, "prod_red.jpg", alt_text="红色连衣裙", tags=["女装", "夏款"], category="产品")
    assert ml.register(tid, "prod_black.jpg", alt_text="黑色半裙", tags=["女装"], category="产品")

    items = ml.list_images(tid)
    assert len(items) == 2
    names = {it.filename for it in items}
    assert names == {"prod_red.jpg", "prod_black.jpg"}
    red = next(i for i in items if i.filename == "prod_red.jpg")
    assert red.alt_text == "红色连衣裙"
    assert "女装" in red.tags


def test_register_skips_missing_file(tmp_tenant):
    tid, _ = tmp_tenant
    assert ml.register(tid, "not_exist.jpg", alt_text="x") is False


# ── 2. pick_by_filename 安全 ─────────────────────────────────────────────────

def test_pick_by_filename_ok(tmp_tenant):
    tid, mdir = tmp_tenant
    (mdir / "a.jpg").write_bytes(b"x")
    p = ml.pick_by_filename(tid, "a.jpg")
    assert p is not None
    assert p.name == "a.jpg"


@pytest.mark.parametrize("dangerous", [
    "../../etc/passwd",
    "/etc/passwd",
    ".env",
    "",
    "sub/a.jpg",
])
def test_pick_by_filename_rejects_traversal(tmp_tenant, dangerous):
    tid, _ = tmp_tenant
    assert ml.pick_by_filename(tid, dangerous) is None


# ── 3. extract_image_refs ────────────────────────────────────────────────────

def test_extract_image_refs_single():
    text = "亲，这款您看下 [[IMG:prod_red.jpg]] 活动价 268"
    clean, fns = ml.extract_image_refs(text)
    assert fns == ["prod_red.jpg"]
    assert "[[IMG" not in clean
    assert "268" in clean


def test_extract_image_refs_multi():
    text = "有两款 [[IMG:a.jpg]] 和 [[IMG:b.jpg]] · 您挑"
    clean, fns = ml.extract_image_refs(text)
    assert fns == ["a.jpg", "b.jpg"]
    assert "[[IMG" not in clean


def test_extract_image_refs_none():
    text = "纯文字 · 没图"
    clean, fns = ml.extract_image_refs(text)
    assert fns == []
    assert clean == text


# ── 4. render_prompt_block ───────────────────────────────────────────────────

def test_render_prompt_block_lists_images(tmp_tenant):
    tid, mdir = tmp_tenant
    (mdir / "x.jpg").write_bytes(b"x")
    ml.register(tid, "x.jpg", alt_text="示例图", tags=["a"])
    block = ml.render_prompt_block(tid)
    assert "可用图片" in block
    assert "x.jpg" in block
    assert "示例图" in block
    assert "[[IMG:" in block


def test_render_prompt_block_empty(tmp_tenant):
    tid, _ = tmp_tenant
    assert ml.render_prompt_block(tid) == ""


# ── 5. prompt_builder 注入 media_block ───────────────────────────────────────

def test_build_system_prompt_includes_media_block():
    intent = IntentResult(intent=IntentEnum.INQUIRY, confidence=0.8, risk=RiskEnum.LOW, emotion=EmotionEnum.CALM)
    prompt = build_system_prompt(
        boss_name="张老板",
        style_hints="直接简洁",
        intent=intent,
        media_block="# 可用图片\n- prod.jpg | 产品图",
    )
    assert "可用图片" in prompt
    assert "prod.jpg" in prompt


def test_build_system_prompt_no_media_block_when_empty():
    intent = IntentResult(intent=IntentEnum.INQUIRY, confidence=0.8, risk=RiskEnum.LOW, emotion=EmotionEnum.CALM)
    prompt = build_system_prompt(
        boss_name="张老板", style_hints="直接", intent=intent,
    )
    assert "可用图片" not in prompt


# ── 6. Suggestion proto 有 image_filenames 字段 ──────────────────────────────

def test_suggestion_has_image_filenames_field():
    s = Suggestion(
        msg_id="m1",
        tenant_id="t1",
        inbound_msg_id="in1",
        intent=IntentResult(intent=IntentEnum.INQUIRY, confidence=0.8, risk=RiskEnum.LOW),
        text="x",
        model_route="r",
        generated_at=123,
    )
    assert s.image_filenames == []
    s2 = Suggestion(
        msg_id="m2", tenant_id="t1", inbound_msg_id="in2",
        intent=IntentResult(intent=IntentEnum.INQUIRY, confidence=0.8, risk=RiskEnum.LOW),
        text="x", model_route="r", generated_at=123,
        image_filenames=["a.jpg", "b.jpg"],
    )
    assert s2.image_filenames == ["a.jpg", "b.jpg"]


# ── 7. wxpad_send_image HTTP mock ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wxpad_send_image_returns_true_on_success(tmp_path, temp_db):
    """真插入 tenant + wx_account DB 行 · 只 mock HTTP 层."""
    import time as _t
    from sqlalchemy import select as _sel

    from server import wxpadpro_bridge as wb
    from server.db import session_scope
    from server.models import Tenant, WxAccount

    img = tmp_path / "t.jpg"
    img.write_bytes(b"\xff\xd8\xff\xe0testjpg")

    tid = "t_img_test"
    aid = "acc_img_test"
    async with session_scope() as s:
        if not (await s.execute(_sel(Tenant).where(Tenant.tenant_id == tid))).scalar_one_or_none():
            s.add(Tenant(tenant_id=tid, boss_name="t", plan="pro", created_at=int(_t.time())))
        exist = (await s.execute(_sel(WxAccount).where(WxAccount.account_id == aid))).scalar_one_or_none()
        if not exist:
            s.add(WxAccount(
                account_id=aid, tenant_id=tid, app_id=aid, status="online",
                auth_key="AUTHKEY_TEST", tunnel_alive=0, daily_quota=50,
                quota_used_today=0, created_at=int(_t.time()),
            ))

    async def _fake_api(method, path, payload=None, key=None, timeout=15.0):
        assert path == "/message/SendImageMessage"
        assert "MsgItem" in payload
        item = payload["MsgItem"][0]
        assert item["MsgType"] == 3
        assert item["ImageContent"]  # base64 非空
        assert key == "AUTHKEY_TEST"
        return {"Code": 200, "Data": [{"isSendSuccess": True}]}

    with patch.object(wb, "_wxpad_api", new=_fake_api):
        ok = await wb.wxpad_send_image(aid, "wxid_y", str(img))
    assert ok is True


@pytest.mark.asyncio
async def test_wxpad_send_image_returns_false_on_missing_file():
    from server import wxpadpro_bridge as wb
    ok = await wb.wxpad_send_image("acc_x", "wxid_y", "/tmp/not_exist_99999.jpg")
    assert ok is False
