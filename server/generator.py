"""ReplyGenerator · 调 hermes_bridge 生成 + 禁用词检查 + dedup 重写。"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from server.audit import audit
from server.hermes_bridge import HermesBridge
from server.model_router import ModelRouter
from server.prompt_builder import build_system_prompt, build_user_prompt
from server.risk_check import contains_forbidden_word, is_duplicate
from server.tenant import TenantManager
from shared.errors import ForbiddenWordError
from shared.proto import InboundMsg, IntentResult, Suggestion

logger = logging.getLogger(__name__)

MAX_REWRITE_ATTEMPTS = 3


class ReplyGenerator:
    def __init__(
        self,
        hermes: HermesBridge,
        router: ModelRouter,
        tenants: TenantManager,
    ):
        self.hermes = hermes
        self.router = router
        self.tenants = tenants

    async def generate(
        self,
        msg: InboundMsg,
        intent: IntentResult,
        customer_profile_block: str = "",
        knowledge_block: str = "",
        industry_block: str = "",
        psych_block: str = "",
    ) -> Suggestion:
        tenant = self.tenants.get(msg.tenant_id)
        route = self.router.route(msg.tenant_id, intent)

        # Wave 10: 加载 tenant 训练产物(style_pack / dialogue_bank / faq_bank)
        style_pack = None
        few_shot_block = ""
        special_rules = ""
        try:
            from pathlib import Path as _Path
            lora_root = _Path(f"tenants/{msg.tenant_id}/boss_super_lora")

            # style_pack.json
            sp_path = lora_root / "style_pack.json"
            if sp_path.exists():
                import json as _json
                style_pack = _json.loads(sp_path.read_text(encoding="utf-8"))

            # dialogue_bank: BGE few-shot 检索
            db_path = lora_root / "dialogue_bank.jsonl"
            if db_path.exists():
                from server.dialogue_bank import DialogueBank
                bank = DialogueBank(msg.tenant_id, bank_path=db_path)
                bank.load()
                if bank.pairs:
                    top_pairs = bank.retrieve(msg.text, top_k=5)
                    few_shot_block = bank.to_few_shot_block(top_pairs)

            # faq_bank: 如果有对应 FAQ 也注入到 knowledge
            faq_path = lora_root / "faq_bank.json"
            if faq_path.exists():
                import json as _json
                faq_data = _json.loads(faq_path.read_text(encoding="utf-8"))
                if isinstance(faq_data, dict) and faq_data.get("faqs"):
                    special_rules = str(faq_data.get("special_rules", ""))
        except Exception as e:
            logger.debug("wave10 tenant data load failed (non-blocking): %s", e)

        # Wave 14 · 素材库 block · 让 AI 知道可引用哪些图
        media_block = ""
        try:
            from server.media_library import render_prompt_block as _render_media_block
            media_block = _render_media_block(msg.tenant_id)
        except Exception as e:
            logger.debug("wave14 media block load failed (non-blocking): %s", e)

        # 集中 prompt · 防地理/家庭/年龄幻觉 · 风格继承 + 客户档案 + RAG + 行业 + 心理学 + 素材库
        system = build_system_prompt(
            boss_name=tenant.boss_name,
            style_hints=tenant.style_hints,
            intent=intent,
            sender_name=msg.sender_name,
            customer_profile_block=customer_profile_block,
            knowledge_block=knowledge_block,
            industry_block=industry_block,
            psych_block=psych_block,
            style_pack=style_pack,
            few_shot_block=few_shot_block,
            special_rules=special_rules,
            media_block=media_block,
        )
        prompt = build_user_prompt(msg.sender_name, msg.text)

        text = ""
        rewrite_count = 0
        forbidden_hit = False
        sim_passed = True

        for attempt in range(MAX_REWRITE_ATTEMPTS):
            text = await self.hermes.respond(
                prompt=prompt,
                tenant_id=msg.tenant_id,
                model_route=route,
                system=system,
                max_tokens=300,
            )

            forbidden_hit, hit_words = contains_forbidden_word(text)
            if forbidden_hit:
                logger.warning("forbidden word hit: %s · attempt %d", hit_words, attempt + 1)
                rewrite_count += 1
                system += "\n\n[重写要求] 上次回复命中禁用词，避免绝对化承诺。"
                continue

            if await is_duplicate(text, msg.tenant_id):
                sim_passed = False
                rewrite_count += 1
                system += "\n\n[重写要求] 上次回复与历史相似，请换个说法。"
                continue

            sim_passed = True
            forbidden_hit = False
            break

        if forbidden_hit:
            await audit.log(
                actor="server",
                action="forbidden_word_blocked",
                tenant_id=msg.tenant_id,
                meta={"text": text, "rewrite_count": rewrite_count},
            )
            raise ForbiddenWordError(f"无法生成无风险回复（重写 {rewrite_count} 次仍命中）")

        suggestion = Suggestion(
            msg_id=f"sug_{uuid.uuid4().hex[:16]}",
            tenant_id=msg.tenant_id,
            inbound_msg_id=self._inbound_msg_id(msg),
            intent=intent,
            text=text,
            model_route=route,
            generated_at=int(time.time()),
            similarity_check_passed=sim_passed,
            rewrite_count=rewrite_count,
            forbidden_word_hit=False,
        )
        return suggestion

    @staticmethod
    def _inbound_msg_id(msg: InboundMsg) -> str:
        return f"in_{msg.tenant_id}_{msg.timestamp}_{msg.sender_id[:8]}"
