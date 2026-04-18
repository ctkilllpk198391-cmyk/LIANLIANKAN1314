"""S7 · 交叉销售引擎 · 独立模块 · 不修改现有文件。

数据流：
  customer_profile.purchase_history → 最近购买 sku → KB 召回相关 chunk
  → 候选产品解析 → 相关度 + 标签排序 → top 1-2 ProductRec
  → maybe_append_to_reply 决策插入/不插

风控：
  - intent=COMPLAINT/SENSITIVE → 不推
  - 同 (tenant_id, chat_id) 当天最多 1 次
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Optional

from shared.types import IntentEnum

logger = logging.getLogger(__name__)

# ── 风控：禁止推荐的 intent ────────────────────────────────────────────────────
_NO_SELL_INTENTS = {IntentEnum.COMPLAINT, IntentEnum.SENSITIVE}

# ── 休眠判断：30 天未联系视为休眠客户，不主动推销 ─────────────────────────────
_DORMANT_DAYS = 30


@dataclass
class ProductRec:
    sku: str
    name: str
    reason: str   # 推荐理由（自然话术，拼到回复里）
    score: float


class CrossSellEngine:
    """交叉销售引擎 · 轻量 · mock 友好。"""

    def __init__(
        self,
        knowledge_base=None,
        max_per_day_per_chat: int = 1,
    ):
        self._kb = knowledge_base
        self._max = max_per_day_per_chat
        # key=(tenant_id, chat_id, date_str) → int 推荐次数
        self._daily: dict[tuple[str, str, str], int] = {}

    # ── 推荐主流程 ─────────────────────────────────────────────────────────────

    async def recommend(
        self,
        tenant_id: str,
        customer_profile,          # CustomerProfileSnapshot
        current_intent: IntentEnum,
        last_message_text: str = "",
    ) -> list[ProductRec]:
        """基于历史购买 + KB 召回 + intent，返回 0-2 个推荐。"""

        # 风控：敏感意图不推
        if current_intent in _NO_SELL_INTENTS:
            logger.debug("cross_sell skip: intent=%s", current_intent)
            return []

        # 风控：休眠客户不推（最后联系 >= 30 天）
        if _is_dormant(customer_profile):
            logger.debug("cross_sell skip: dormant customer %s", customer_profile.chat_id)
            return []

        # 取最近购买 sku 作为查询词
        purchase_history: list[dict] = customer_profile.purchase_history or []
        if not purchase_history:
            logger.debug("cross_sell skip: no purchase history")
            return []

        query_text = _build_query(purchase_history, last_message_text)
        if not query_text:
            return []

        # KB 召回
        kb = self._kb
        if kb is None:
            return []

        chunks = await kb.query(tenant_id, query_text, top_k=5, min_score=0.0)
        if not chunks:
            return []

        # 从 chunk 解析候选产品
        already_bought = {item.get("sku", "") for item in purchase_history}
        candidates = _parse_candidates(chunks, already_bought)
        if not candidates:
            return []

        # 按 score + 客户标签加权排序
        tags = set(customer_profile.tags or [])
        scored = _rank_candidates(candidates, tags)

        # top 1-2
        return scored[:2]

    # ── 回复插入决策 ────────────────────────────────────────────────────────────

    async def maybe_append_to_reply(
        self,
        original_reply: str,
        recs: list[ProductRec],
        chat_id: str,
        tenant_id: str,
    ) -> str:
        """决策：插入还是不插。

        - 无推荐 → 原样返回
        - 当天该 chat 已推过 → 不插
        - 否则：自然话术加在 reply 末尾
        """
        if not recs:
            return original_reply

        date_str = time.strftime("%Y-%m-%d")
        key = (tenant_id, chat_id, date_str)
        count = self._daily.get(key, 0)

        if count >= self._max:
            logger.debug("cross_sell skip: daily limit reached for %s/%s", tenant_id, chat_id)
            return original_reply

        # 取第一个推荐拼话术
        rec = recs[0]
        suffix = _format_suffix(rec)

        self._daily[key] = count + 1
        logger.info("cross_sell inserted: tenant=%s chat=%s sku=%s", tenant_id, chat_id, rec.sku)

        # 末尾加一个换行再拼（保持自然）
        reply = original_reply.rstrip()
        return f"{reply}\n\n{suffix}"


# ── 内部辅助函数 ───────────────────────────────────────────────────────────────

def _is_dormant(profile) -> bool:
    """最后一次联系 >= DORMANT_DAYS 视为休眠。"""
    days = getattr(profile, "days_since_last", None)
    if days is None:
        return False
    return days >= _DORMANT_DAYS


def _build_query(purchase_history: list[dict], last_message_text: str) -> str:
    """取最近 3 条购买 sku 拼查询词，加上当前消息文本。"""
    recent_skus = [
        item.get("sku", "")
        for item in sorted(purchase_history, key=lambda x: x.get("date", 0), reverse=True)
        if item.get("sku")
    ][:3]

    parts = [s for s in recent_skus if s and s != "unknown"]
    if last_message_text.strip():
        parts.append(last_message_text.strip())

    return " ".join(parts)


def _parse_candidates(chunks, already_bought: set[str]) -> list[ProductRec]:
    """从 chunk 文本解析候选产品。

    约定：chunk 第一行/标题视为产品名称（# 标题 或 直接第一行）。
    sku 取首行的英文/数字 slug，若无则用首行截断。
    """
    seen_skus: set[str] = set()
    candidates: list[ProductRec] = []

    for chunk in chunks:
        text: str = chunk.text.strip()
        if not text:
            continue

        first_line = text.split("\n")[0].strip()
        # 去 markdown # 号
        name = re.sub(r"^#+\s*", "", first_line).strip()
        if not name:
            continue

        # 提取 sku：优先英数字母组合，否则用名称前 20 字符 slugify
        sku_match = re.search(r"\b([A-Za-z0-9][-A-Za-z0-9_]{2,})\b", name)
        sku = sku_match.group(1).lower() if sku_match else re.sub(r"[^\w]", "_", name)[:20]

        # 去重 + 排除已购
        if sku in seen_skus or sku in already_bought:
            continue
        seen_skus.add(sku)

        candidates.append(
            ProductRec(
                sku=sku,
                name=name,
                reason=f"与您之前购买的商品相关",
                score=chunk.score,
            )
        )

    return candidates


def _rank_candidates(candidates: list[ProductRec], customer_tags: set[str]) -> list[ProductRec]:
    """按 score 降序排序 · 若客户标签命中产品名则 +0.1 奖励。"""
    def _sort_key(rec: ProductRec) -> float:
        bonus = 0.1 if any(tag.lower() in rec.name.lower() for tag in customer_tags) else 0.0
        return rec.score + bonus

    return sorted(candidates, key=_sort_key, reverse=True)


def _format_suffix(rec: ProductRec) -> str:
    """生成自然推荐话术。"""
    return f"对了~ 你之前买过的款式，这次新到了「{rec.name}」也很适合你哦~ 有兴趣的话可以看看~"
