"""judge LLM · 调 hermes_bridge 让 DeepSeek-R1/Claude 当评委评估 LoRA 输出。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from server.hermes_bridge import HermesBridge

logger = logging.getLogger(__name__)


@dataclass
class JudgeScore:
    style_match: float
    naturalness: float
    on_topic: float
    comment: str

    @property
    def overall(self) -> float:
        return (self.style_match * 0.5 + self.naturalness * 0.3 + self.on_topic * 0.2)


JUDGE_PROMPT_TEMPLATE = """你是一个微信聊天风格评委。给定客户消息和两条回复（一条是老板真实回复，一条是 AI 生成），
判断 AI 生成的回复是否符合老板的风格、自然度、话题相关性。

客户消息: {customer_msg}
老板真实回复: {boss_real}
AI 生成回复: {ai_generated}

输出严格 JSON（不要任何其他文字），格式：
{{"style_match": 0.X, "naturalness": 0.X, "on_topic": 0.X, "comment": "简短说明"}}
其中三个分数取值 0-1。"""


JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


class JudgeLLM:
    def __init__(self, hermes: HermesBridge, model_route: str = "judge_deepseek"):
        self.hermes = hermes
        self.model_route = model_route

    async def judge(
        self,
        customer_msg: str,
        boss_real: str,
        ai_generated: str,
        tenant_id: str = "judge_global",
    ) -> JudgeScore:
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            customer_msg=customer_msg,
            boss_real=boss_real,
            ai_generated=ai_generated,
        )
        text = await self.hermes.respond(
            prompt=prompt,
            tenant_id=tenant_id,
            model_route=self.model_route,
            max_tokens=200,
        )
        return self._parse_score(text)

    @staticmethod
    def _parse_score(text: str) -> JudgeScore:
        m = JSON_RE.search(text)
        if not m:
            logger.warning("judge LLM 返回非 JSON · 兜底 0.5: %s", text[:80])
            return JudgeScore(0.5, 0.5, 0.5, "judge_parse_failed")
        try:
            data = json.loads(m.group(0))
            return JudgeScore(
                style_match=float(data.get("style_match", 0.5)),
                naturalness=float(data.get("naturalness", 0.5)),
                on_topic=float(data.get("on_topic", 0.5)),
                comment=str(data.get("comment", "")),
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("judge JSON parse failed: %s", e)
            return JudgeScore(0.5, 0.5, 0.5, f"judge_error: {e}")


@dataclass
class EvalReportRow:
    customer_msg: str
    boss_real: str
    ai_generated: str
    score: JudgeScore


def render_eval_report(
    tenant_id: str,
    rows: list[EvalReportRow],
    forbidden_word_rate: float = 0.0,
    over_length_rate: float = 0.0,
) -> str:
    if not rows:
        return f"# {tenant_id} LoRA 评估报告\n\n样本为空。"

    avg_style = sum(r.score.style_match for r in rows) / len(rows)
    avg_nat = sum(r.score.naturalness for r in rows) / len(rows)
    avg_topic = sum(r.score.on_topic for r in rows) / len(rows)
    avg_overall = sum(r.score.overall for r in rows) / len(rows)

    failures = sorted(rows, key=lambda r: r.score.overall)[:3]

    lines = [
        f"# {tenant_id} LoRA 评估报告",
        "",
        f"## 数据集",
        f"- 样本数: {len(rows)}",
        "",
        f"## 主要指标",
        f"| 指标 | 值 | 目标 | 状态 |",
        f"|---|---|---|---|",
        f"| 风格相似度 | {avg_style:.2f} | ≥ 0.50 | {'✅' if avg_style >= 0.5 else '❌'} |",
        f"| 自然度 | {avg_nat:.2f} | ≥ 0.70 | {'✅' if avg_nat >= 0.7 else '❌'} |",
        f"| 话题相关 | {avg_topic:.2f} | ≥ 0.80 | {'✅' if avg_topic >= 0.8 else '❌'} |",
        f"| 综合得分 | {avg_overall:.2f} | ≥ 0.60 | {'✅' if avg_overall >= 0.6 else '❌'} |",
        f"| 禁用词命中率 | {forbidden_word_rate:.2%} | ≤ 1% | {'✅' if forbidden_word_rate <= 0.01 else '❌'} |",
        f"| 超长率 | {over_length_rate:.2%} | ≤ 1% | {'✅' if over_length_rate <= 0.01 else '❌'} |",
        "",
        f"## 失败案例 Top 3",
    ]
    for i, row in enumerate(failures, 1):
        lines.extend(
            [
                f"### {i}. overall={row.score.overall:.2f}",
                f"- 客户: {row.customer_msg[:60]}",
                f"- 老板真: {row.boss_real[:60]}",
                f"- AI 生: {row.ai_generated[:60]}",
                f"- 评委: {row.score.comment}",
                "",
            ]
        )

    return "\n".join(lines)
