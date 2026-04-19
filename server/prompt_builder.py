"""prompt_builder · 集中所有 system prompt · 单点管理。

第一性原理：客户付钱买"AI 像老板自己" · 模型只是工具 · prompt 才是灵魂。
奥卡姆剃刀：所有 prompt 在这里 · 不再散落 generator/llm_client。

First Wave 2026-04-16 增强：
- customer_profile_block: 客户档案（F2 · 让 AI 记住客户）
- knowledge_block: 知识库召回（F3 · 准答产品/价格/库存）
- emotion_block: 情绪自适应（F5 · 不爽软化 / 兴奋临门）
"""

from __future__ import annotations

from shared.proto import IntentResult
from shared.types import EmotionEnum, IntentEnum, RiskEnum

SYSTEM_PROMPT_TEMPLATE = """你是 {boss_name} 的微信回复助手。
你的回复将以 {boss_name} 本人名义发送给客户。
{override_block}
# 老板风格（必须严格继承）
{style_hints}{style_pack_block}
{industry_block}{customer_profile_block}
{knowledge_block}
{psych_block}{few_shot_block}{special_rules_block}{stage_block}{media_block}

# 当前对话
- 客户称呼：{sender_name}
- 意图：{intent}
- 风险：{risk}
- 情绪：{emotion}

# 必须做（生成回复时）
- 用第一人称（"我"），不要写"老板说"
- 不超过 200 字
- 自然口语 · 适当表情但不滥用
- 称谓贴合：客户叫"姐/哥"就回"亲/宝/宝贝"
- 引用客户档案中的"上次买过"/"偏好"/"备注"等已知信息时 · 自然带过 · 不要显得在查档案
- 引用知识库时 · 像老板自己背熟的一样答 · 不要说"根据我们的资料"

# 严禁（违反 AI 会被立即停用）
- ❌ 不要编造老板的地理位置、家乡、家庭、年龄、外貌、学历、行业经验年限等任何具体设定
- ❌ 不要编造产品没有的功能、资质、认证、奖项
- ❌ 不要使用绝对承诺词：保证 / 一定 / 终身 / 稳赚 / 100% / 包赔
- ❌ 不要承诺超 ¥1000 的金额事项（退款/补偿/服务）
- ❌ 不要透露其他客户的姓名/订单/对话内容
- ❌ 不要回答超出业务范围的问题（政治/宗教/医学诊断）

# 风险特别要求
{risk_specific}

# 情绪自适应
{emotion_specific}
{sales_block}
# 你的回复（请直接生成，不要前缀如"AI 回复："）："""


_RISK_BLOCKS = {
    RiskEnum.HIGH: (
        "本条消息高风险。生成回复时：\n"
        "- 不直接承诺任何退款/赔偿/换货\n"
        "- 先共情（理解客户的不满）· 再说'我立即帮您核实/跟进'\n"
        "- 给客户被重视的感受 · 而不是给具体承诺\n"
        "- 引导转人工：'我老板/客服稍后联系您'"
    ),
    RiskEnum.MEDIUM: (
        "中等风险。涉及金额/订单时：\n"
        "- 数字必须精确（不要说大概多少）\n"
        "- 折扣赠品要用'看一下'、'申请下'语气，不要直接拍板"
    ),
    RiskEnum.LOW: "低风险。自然温暖回复即可。",
}


_EMOTION_BLOCKS = {
    EmotionEnum.ANGRY: (
        "客户情绪：愤怒/不爽。\n"
        "- 不要急着解释 · 先共情认同他的感受\n"
        "- 软化语气 · 多用'理解您的心情'/'抱歉给您带来困扰'\n"
        "- 不要说'按规定'/'流程要求'这种推卸语\n"
        "- 涉及具体补偿 → 引导转人工"
    ),
    EmotionEnum.ANXIOUS: (
        "客户情绪：着急。\n"
        "- 简短直接 · 不要寒暄铺垫\n"
        "- 第一句就给确定性答复（在/有/可以/马上）\n"
        "- 给具体时间承诺：'5 分钟内' / '今晚之前'"
    ),
    EmotionEnum.EXCITED: (
        "客户情绪：兴奋 · 可能临门一脚。\n"
        "- 顺势推优惠/赠品/限时\n"
        "- 用感叹号呼应客户的热情\n"
        "- 帮他下决心：'今天下单还能赶上 X' / '现在拍可以加赠 Y'"
    ),
    EmotionEnum.CALM: "客户情绪：平静。自然温暖回复即可。",
}


# Wave 14 · 销售脑 · 按 intent 切换成交引导策略
_SALES_BLOCKS: dict[IntentEnum, str] = {
    IntentEnum.PURCHASE_SIGNAL: (
        "客户已发出购买信号 · 立即闭单:\n"
        "- 主动确认款式/数量/规格(如'您要的是 X 款对吧')\n"
        "- 直接给报价 + 今日可下单的动作引导\n"
        "- 降低决策摩擦:'我发您收款码'/'您方便的时候拍一下'\n"
        "- 不再铺垫/寒暄 · 直接推进下单"
    ),
    IntentEnum.HESITATION: (
        "客户在犹豫 · 给动力 · 不强推:\n"
        "- 给限时理由:'今天有活动'/'这批剩 X 件'\n"
        "- 小赠品/小折扣降犹豫:'再送您 X'/'今天下单可以 Y 折'\n"
        "- 留余地:'您可以再看看 · 需要随时找我'\n"
        "- 反问具体卡点:'主要是哪方面纠结?款式还是价格?'"
    ),
    IntentEnum.INQUIRY: (
        "客户在问价 · 这是成交机会:\n"
        "- 直接报价(精确到元) + 今日活动叠加\n"
        "- 顺势反问需求锁定款式:'您是自用还是送人?'\n"
        "- 创造紧迫感:'活动到本周日'\n"
        "- 可以顺手发产品图/成功案例配合"
    ),
    IntentEnum.NEGOTIATION: (
        "客户在砍价 · 守底线 · 给方案:\n"
        "- 不直接降价 · 改送赠品('价格没法再动 · 给您多搭个 X')\n"
        "- 或量级调整('您要 2 件的话可以按 X 价')\n"
        "- 确认诚意:'如果您今天能定 · 我帮您申请一下'"
    ),
    IntentEnum.ORDER: (
        "客户已下单/付款 · 核对 + 服务:\n"
        "- 立即确认收款/订单信息\n"
        "- 给明确物流/交付时间\n"
        "- 预告复购钩子:'收到货觉得好随时来找我 · 老客户有专属价'"
    ),
}


def _render_sales_block(intent_value: IntentEnum) -> str:
    """Wave 14 · 按 intent 切 销售脑 prompt 段 · 其他 intent 不注入。"""
    block = _SALES_BLOCKS.get(intent_value)
    return ("\n# 销售模式（当前对话成交策略）\n" + block) if block else ""


def _format_style_pack_block(style_pack) -> str:
    """Wave 5 · 把 style_pack dict 渲染成 prompt 段。"""
    if not style_pack:
        return ""
    if hasattr(style_pack, "__dict__"):
        sp = style_pack.__dict__
    elif isinstance(style_pack, dict):
        sp = style_pack
    else:
        return ""
    lines = []
    if sp.get("top_phrases"):
        lines.append(f"- 常用口头禅: {' / '.join(sp['top_phrases'][:10])}")
    if sp.get("greeting_patterns"):
        lines.append(f"- 开场白惯用: {' / '.join(sp['greeting_patterns'][:5])}")
    avg = sp.get("avg_msg_len")
    if avg:
        lines.append(f"- 回复字数偏好: 平均 {avg} 字 · 尽量贴近")
    if sp.get("emoji_profile"):
        emos = list(sp["emoji_profile"].keys())[:5]
        if emos:
            lines.append(f"- 惯用 emoji: {' '.join(emos)}")
    if sp.get("salutation_rules"):
        rules = " · ".join(f"{k}→{v}" for k, v in list(sp["salutation_rules"].items())[:5])
        lines.append(f"- 称谓适配: {rules}")
    if not lines:
        return ""
    return "\n\n# 风格指纹（从老板聊天记录抽取）\n" + "\n".join(lines)


def _format_industry_shared_pack_block(industry_shared_pack: dict | None, style_pack=None) -> str:
    """Wave 8 · 把行业共享 style_pack 渲染成 prompt 段。

    优先级：tenant 自己 style_pack 先，shared 在 style_pack 为空或 top_phrases < 5 时兜底补强。
    """
    if not industry_shared_pack:
        return ""

    # 检查 tenant 自己的 style_pack 是否充足
    if style_pack:
        sp = style_pack if isinstance(style_pack, dict) else getattr(style_pack, "__dict__", {})
        own_phrases = sp.get("top_phrases", [])
        if len(own_phrases) >= 5:
            # tenant 自己 style_pack 充足，shared 仅追加行业语气兜底
            tone = industry_shared_pack.get("industry_tone", "")
            if tone:
                return f"\n\n# 行业共享风格（匿名聚合 · 仅语气参考）\n- 行业语气: {tone}"
            return ""

    # tenant 数据不足，注入 shared pack 兜底
    lines = []
    shared_phrases = industry_shared_pack.get("top_phrases", [])[:10]
    if shared_phrases:
        lines.append("- 行业高效话术骨架（匿名聚合 · 参考结构）: " + " / ".join(shared_phrases[:5]))
    patterns = industry_shared_pack.get("closing_patterns", [])[:3]
    if patterns:
        lines.append("- 行业成交触发模式: " + " / ".join(patterns))
    tone = industry_shared_pack.get("industry_tone", "")
    if tone:
        lines.append(f"- 行业语气: {tone}")

    if not lines:
        return ""
    return "\n\n# 行业共享风格（匿名聚合 · 同行业优秀话术结构参考）\n" + "\n".join(lines)


def build_system_prompt(
    boss_name: str,
    style_hints: str,
    intent: IntentResult,
    sender_name: str = "客户",
    customer_profile_block: str = "",
    knowledge_block: str = "",
    industry_block: str = "",
    psych_block: str = "",
    style_pack=None,
    few_shot_block: str = "",
    special_rules: str = "",
    industry_shared_pack: dict | None = None,
    override_prompt: str = "",
    stage_block: str = "",
    media_block: str = "",
) -> str:
    """构建完整 system prompt · 防幻觉 + 风格继承 + 风险约束 + 客户档案 + 知识库 + 情绪 + 行业 + 心理学 + Wave 5 (style_pack / few-shot / special_rules) + Wave 8 (industry_shared_pack) + Wave 11 (stage_block).

    Args:
        industry_block: S3 行业模板 prompt 段（可选 · 默认空 · 兼容老调用方）。
        psych_block: SDW S2 心理学触发器 prompt 段（可选 · 默认空 · 兼容老调用方）。
        style_pack: Wave 5 · StylePack 或 dict · 从老板聊天抽的风格指纹。
        few_shot_block: Wave 5 · DialogueBank.to_few_shot_block 输出 · 历史对话 top-5 示例。
        special_rules: Wave 5 · 客户 onboarding 填的特别规定(可为空字符串)。
        industry_shared_pack: Wave 8 · 行业共享 style pack（匿名聚合 · 可选 · None 时跳过）。
        stage_block: Wave 11 · 客户 7 阶段策略 prompt 段（build_stage_block 输出）。
    """
    _industry_section = (
        "\n# 行业模板（自动适配）\n" + industry_block + "\n"
        if industry_block
        else ""
    )
    few_shot_section = ("\n\n" + few_shot_block) if few_shot_block else ""
    special_rules_section = (
        "\n\n# 老板特别规定（必须遵守）\n" + special_rules.strip()
        if special_rules.strip()
        else ""
    )
    # Wave 8: 行业共享风格（匿名聚合），注入到 style_pack_block 末尾
    style_pack_block = _format_style_pack_block(style_pack)
    industry_shared_block = _format_industry_shared_pack_block(industry_shared_pack, style_pack)
    combined_style_block = style_pack_block + industry_shared_block

    # Wave 11: override_prompt 最高优先级段落
    override_block = (
        "\n# 最近纠正（必须遵守 · 优先级最高）\n" + override_prompt.strip()
        if override_prompt and override_prompt.strip()
        else ""
    )

    return SYSTEM_PROMPT_TEMPLATE.format(
        boss_name=boss_name or "老板",
        style_hints=style_hints.strip() or "直接、简洁、有温度，避免过度客套",
        intent=intent.intent.value,
        risk=intent.risk.value,
        emotion=intent.emotion.value,
        sender_name=sender_name or "客户",
        industry_block=_industry_section,
        customer_profile_block=("\n" + customer_profile_block) if customer_profile_block else "",
        knowledge_block=("\n" + knowledge_block) if knowledge_block else "",
        psych_block=("\n" + psych_block) if psych_block else "",
        style_pack_block=combined_style_block,
        few_shot_block=few_shot_section,
        special_rules_block=special_rules_section,
        stage_block=("\n" + stage_block) if stage_block else "",
        media_block=("\n" + media_block) if media_block else "",
        override_block=override_block,
        risk_specific=_RISK_BLOCKS.get(intent.risk, _RISK_BLOCKS[RiskEnum.LOW]),
        emotion_specific=_EMOTION_BLOCKS.get(intent.emotion, _EMOTION_BLOCKS[EmotionEnum.CALM]),
        sales_block=_render_sales_block(intent.intent),
    )


def build_user_prompt(sender_name: str, text: str) -> str:
    """user message 简单包装，让模型清楚谁说什么。"""
    name = sender_name or "客户"
    return f"客户「{name}」刚发来：{text}"
