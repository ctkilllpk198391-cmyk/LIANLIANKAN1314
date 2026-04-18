"""test_industry_router · S3 行业模板池 + 自动检测路由测试。

≥6 用例覆盖：
- 6 行业全加载
- 每行业返回非空 prompt block
- list_industries 返回正确列表
- mock LLM detect 解析正确
- 未知行业返回空字符串
- 每个 markdown 含必须章节
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.industry_router import IndustryRouter, _parse_industry_from_llm_reply


# ------------------------------------------------------------------
# Fixtures

@pytest.fixture(scope="module")
def router():
    """使用默认模板目录初始化路由器（真实文件）。"""
    return IndustryRouter()


# ------------------------------------------------------------------
# 用例 1: test_load_industries · 6 个全加载且缓存非空

def test_load_industries(router):
    """6 个行业 markdown 都成功加载进缓存。"""
    for industry in IndustryRouter.SUPPORTED:
        block = router.get_prompt_block(industry)
        assert block, f"行业 [{industry}] 的模板加载后为空"


# ------------------------------------------------------------------
# 用例 2: test_get_prompt_block · 每个行业返回非空 block

def test_get_prompt_block(router):
    """get_prompt_block 对所有 6 个行业都返回有内容的字符串。"""
    for industry in IndustryRouter.SUPPORTED:
        block = router.get_prompt_block(industry)
        assert isinstance(block, str), f"[{industry}] 返回类型非 str"
        assert len(block) > 100, f"[{industry}] 内容太短（<100字），疑似空模板"


# ------------------------------------------------------------------
# 用例 3: test_list_industries · 返回正确列表

def test_list_industries(router):
    """list_industries 返回 list[str] · 包含全部 6 个行业。"""
    industries = router.list_industries()
    assert isinstance(industries, list)
    assert len(industries) == 6
    for name in ["微商", "房产中介", "医美", "教培", "电商", "保险"]:
        assert name in industries, f"[{name}] 不在 list_industries 返回中"


# ------------------------------------------------------------------
# 用例 4: test_detect_with_mock_llm · mock LLM 返"微商" → router 解析正确

@pytest.mark.asyncio
async def test_detect_with_mock_llm(router):
    """detect_from_history 调用 mock LLM · 解析行业 ID 正确。"""
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value="微商")

    sample_msgs = [
        "亲，这款有货吗",
        "包邮吗",
        "能便宜点吗宝",
        "发货多久",
        "有没有买家秀",
    ]
    result = await router.detect_from_history(mock_llm, sample_msgs)
    assert result == "微商", f"期望'微商'，实际返回'{result}'"


# ------------------------------------------------------------------
# 用例 5: test_unknown_industry_returns_empty · 未知行业返回空字符串

def test_unknown_industry_returns_empty(router):
    """get_prompt_block 对未知行业返回空字符串。"""
    assert router.get_prompt_block("宠物用品") == ""
    assert router.get_prompt_block("") == ""
    assert router.get_prompt_block("未知") == ""


# ------------------------------------------------------------------
# 用例 6: test_template_contains_required_sections · 每个 md 含 ## 称谓 · ## 风格 · ## 业务关键词

def test_template_contains_required_sections(router):
    """每个行业 markdown 必须包含三个必要章节标题。"""
    required_sections = ["## 称谓", "## 风格", "## 业务关键词"]
    for industry in IndustryRouter.SUPPORTED:
        block = router.get_prompt_block(industry)
        for section in required_sections:
            assert section in block, (
                f"行业 [{industry}] 缺少必要章节 '{section}'"
            )


# ------------------------------------------------------------------
# 额外用例 7: test_detect_returns_unknown_for_empty_samples

@pytest.mark.asyncio
async def test_detect_returns_unknown_for_empty_samples(router):
    """空样本列表 → 直接返回'未知'，不调用 LLM。"""
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(return_value="微商")

    result = await router.detect_from_history(mock_llm, [])
    assert result == "未知"
    mock_llm.chat.assert_not_called()


# ------------------------------------------------------------------
# 额外用例 8: test_parse_industry_helper · 辅助函数正确解析各类 LLM 回复格式

def test_parse_industry_helper():
    """_parse_industry_from_llm_reply 能解析 LLM 各种回复格式。"""
    supported = IndustryRouter.SUPPORTED

    # 精确匹配
    assert _parse_industry_from_llm_reply("微商", supported) == "微商"
    assert _parse_industry_from_llm_reply("房产中介", supported) == "房产中介"
    assert _parse_industry_from_llm_reply("保险", supported) == "保险"

    # 带前缀/后缀的情况
    assert _parse_industry_from_llm_reply("这是微商行业", supported) == "微商"
    assert _parse_industry_from_llm_reply("  电商  ", supported) == "电商"

    # 真正未知的回答
    assert _parse_industry_from_llm_reply("餐饮", supported) == "未知"
    assert _parse_industry_from_llm_reply("", supported) == "未知"


# ------------------------------------------------------------------
# 额外用例 9: test_prompt_builder_industry_block_integration · prompt_builder 集成

def test_prompt_builder_industry_block_integration(router):
    """build_system_prompt 传入 industry_block 后 prompt 包含行业模板标题。"""
    from server.prompt_builder import build_system_prompt
    from shared.proto import IntentResult
    from shared.types import IntentEnum, RiskEnum

    intent = IntentResult(intent=IntentEnum.GREETING, confidence=0.9, risk=RiskEnum.LOW)
    block = router.get_prompt_block("微商")

    prompt = build_system_prompt(
        boss_name="连大哥",
        style_hints="亲切温暖",
        intent=intent,
        industry_block=block,
    )
    assert "行业模板（自动适配）" in prompt
    assert "## 称谓" in prompt


# ------------------------------------------------------------------
# 额外用例 10: test_prompt_builder_backward_compat · 老调用方不传 industry_block 正常

def test_prompt_builder_backward_compat():
    """build_system_prompt 不传 industry_block 时，老调用方不受影响。"""
    from server.prompt_builder import build_system_prompt
    from shared.proto import IntentResult
    from shared.types import IntentEnum, RiskEnum

    intent = IntentResult(intent=IntentEnum.GREETING, confidence=0.9, risk=RiskEnum.LOW)

    # 不传 industry_block
    prompt = build_system_prompt(
        boss_name="连大哥",
        style_hints="直接",
        intent=intent,
    )
    assert "连大哥" in prompt
    # 不含行业块标题（因为没传）
    assert "行业模板（自动适配）" not in prompt


# ------------------------------------------------------------------
# 额外用例 11: test_detect_with_mock_llm_llm_error · LLM 异常时返回"未知"

@pytest.mark.asyncio
async def test_detect_with_mock_llm_llm_error(router):
    """LLM 抛出异常时 detect_from_history 安全返回'未知'。"""
    mock_llm = MagicMock()
    mock_llm.chat = AsyncMock(side_effect=RuntimeError("模拟 API 超时"))

    result = await router.detect_from_history(mock_llm, ["在吗", "多少钱"])
    assert result == "未知"


# ------------------------------------------------------------------
# 额外用例 12: test_tenant_config_industry_field · TenantConfig 含 industry 字段

def test_tenant_config_industry_field():
    """TenantConfig 新增 industry 字段，默认值'通用'，可被赋值。"""
    from shared.proto import TenantConfig

    # 默认值
    cfg = TenantConfig(tenant_id="t1", boss_name="连大哥")
    assert cfg.industry == "通用"

    # 指定行业
    cfg2 = TenantConfig(tenant_id="t2", boss_name="王姐", industry="微商")
    assert cfg2.industry == "微商"
