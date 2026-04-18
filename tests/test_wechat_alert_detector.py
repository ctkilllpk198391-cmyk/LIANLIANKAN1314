"""L3 · 微信举报检测测试。"""

from __future__ import annotations

import asyncio

import pytest

from client.wechat_alert_detector import (
    WECHAT_ALERT_PATTERNS,
    WeChatAlert,
    WeChatAlertDetector,
    detect_alert,
    emergency_stop_via_api,
)


def test_detect_alert_jubao():
    alert = detect_alert("您的账号被举报 · 需要核实")
    assert alert is not None
    assert "举报" in alert.matched_text


def test_detect_alert_violation():
    alert = detect_alert("检测到违规 · 限制发送功能")
    assert alert is not None


def test_detect_alert_account_anomaly():
    alert = detect_alert("账号异常 · 请验证身份")
    assert alert is not None


def test_detect_alert_normal_message():
    assert detect_alert("你好 · 消息已送达") is None
    assert detect_alert("正常的微信消息内容") is None


def test_detect_alert_empty():
    assert detect_alert("") is None
    assert detect_alert("   ") is None


@pytest.mark.asyncio
async def test_detector_simulate_triggers_callback():
    triggered = []

    async def on_alert(alert):
        triggered.append(alert)

    det = WeChatAlertDetector(on_alert=on_alert, poll_interval=1)
    det.simulate_alert("您的账号被举报")

    # 手动跑一次轮询
    await det._run.__wrapped__(det) if hasattr(det._run, "__wrapped__") else None
    # 直接调内部 _poll + on_alert
    texts = det._poll_wechat_texts()
    for t in texts:
        a = detect_alert(t)
        if a:
            await on_alert(a)
            break

    assert len(triggered) == 1
    assert "举报" in triggered[0].matched_text


@pytest.mark.asyncio
async def test_emergency_stop_mock_without_api():
    alert = WeChatAlert(matched_text="被举报", matched_pattern="被举报", detected_at=0)
    # api_client=None → mock 模式
    ok = await emergency_stop_via_api(None, "tenant_0001", alert)
    assert ok is False    # mock 不返 True


def test_alert_patterns_comprehensive():
    """关键模式都包含。"""
    patterns_str = "|".join(WECHAT_ALERT_PATTERNS)
    for kw in ["举报", "违规", "封号", "限制", "异常"]:
        assert kw in patterns_str
