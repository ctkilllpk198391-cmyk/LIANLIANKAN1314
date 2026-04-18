"""industry_router · 行业模板池 + 自动检测路由。

S3 · Second Wave
- 6 个垂直行业 markdown 模板
- 行业 ID → prompt block
- LLM 自动检测：20 条聊天样本 → 推荐行业
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "industry_templates"

_DETECT_PROMPT_TMPL = """你是一个行业识别专家。
请分析以下微信聊天记录（卖家视角），判断这是哪个行业的销售对话。

聊天样本（{n}条）：
{samples}

候选行业：{industries}

请从候选行业中选出最匹配的一个，或者回答"未知"（如果都不符合）。
只回答行业名称，不要解释，不要加标点，例如：微商"""


class IndustryRouter:
    """行业模板路由器。

    用法：
        router = IndustryRouter()
        block = router.get_prompt_block("微商")
        industry = await router.detect_from_history(llm_client, sample_msgs)
    """

    SUPPORTED = ["微商", "房产中介", "医美", "教培", "电商", "保险"]

    def __init__(self, templates_dir: str | Path | None = None) -> None:
        self._dir = Path(templates_dir) if templates_dir else _DEFAULT_TEMPLATES_DIR
        self._cache: dict[str, str] = {}
        self._load_all()

    # ------------------------------------------------------------------
    # 内部

    def _load_all(self) -> None:
        """启动时预加载全部 markdown 到内存缓存。"""
        for industry in self.SUPPORTED:
            path = self._dir / f"{industry}.md"
            if path.exists():
                self._cache[industry] = path.read_text(encoding="utf-8")
            else:
                logger.warning("行业模板文件不存在: %s", path)
                self._cache[industry] = ""

    # ------------------------------------------------------------------
    # 公开 API

    def get_prompt_block(self, industry_id: str) -> str:
        """返回行业 prompt 段（markdown 全文）。

        未知行业 → 返回空字符串（调用方可安全插入 prompt）。
        """
        if industry_id not in self.SUPPORTED:
            return ""
        return self._cache.get(industry_id, "")

    def list_industries(self) -> list[str]:
        """返回已支持的行业列表。"""
        return list(self.SUPPORTED)

    async def detect_from_history(
        self,
        llm_client,
        sample_msgs: list[str],
        llm_route: str = "deepseek_v32",
    ) -> str:
        """分析 ≤20 条客户聊天样本，推断最匹配行业。

        Args:
            llm_client: 实现 `.chat(prompt) → str` 的 LLM 客户端实例。
            sample_msgs: 聊天文本列表（最多取前 20 条）。
            llm_route: 保留参数，标识使用的模型路由（目前不影响调用逻辑）。

        Returns:
            匹配的 industry_id（在 SUPPORTED 内）或 "未知"。
        """
        samples = sample_msgs[:20]
        if not samples:
            return "未知"

        sample_text = "\n".join(f"{i+1}. {msg}" for i, msg in enumerate(samples))
        industries_str = " / ".join(self.SUPPORTED)

        prompt = _DETECT_PROMPT_TMPL.format(
            n=len(samples),
            samples=sample_text,
            industries=industries_str,
        )

        try:
            raw: str = await llm_client.chat(prompt, max_tokens=20, temperature=0.1)
        except Exception as exc:
            logger.error("detect_from_history LLM 调用失败: %s", exc)
            return "未知"

        # 解析 LLM 回复——只取第一行有效文字
        result = _parse_industry_from_llm_reply(raw, self.SUPPORTED)
        return result


# ------------------------------------------------------------------
# 辅助

def _parse_industry_from_llm_reply(raw: str, supported: list[str]) -> str:
    """从 LLM 返回文本中提取行业名称。

    策略：
    1. 优先精确匹配 SUPPORTED 列表中的行业名
    2. 找到即返回，找不到返回"未知"
    """
    if not raw:
        return "未知"

    # 取第一行，去除多余空白
    first_line = raw.strip().splitlines()[0].strip()

    # 精确匹配
    for industry in supported:
        if industry in first_line:
            return industry

    # 模糊匹配（去掉标点后再试）
    cleaned = re.sub(r"[^\u4e00-\u9fff\w]", "", first_line)
    for industry in supported:
        if industry in cleaned:
            return industry

    return "未知"
