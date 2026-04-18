"""L2 · 灰产场景检测 · 触发即拒绝生成 · 转人工 · audit。

集成点：
  - generator.generate 第一步：客户消息含禁词 → 拒绝 + audit
  - knowledge_base.ingest 第一步：上传内容含禁词 → 拒绝入库
  - admin alert：高频触发 → 推老板（疑似灰产客户）

第一性原理：宁可放走 1% 正常客户 · 不能让 1 个灰产用户毁了我们的服务。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ─── 灰产关键词字典（按类别） ─────────────────────────────────────────────

GRAY_KEYWORDS: dict[str, list[str]] = {
    "gambling": [
        "博彩", "百家乐", "时时彩", "体彩私人", "六合彩", "下注", "押注",
        "棋牌赌", "捕鱼赌", "幸运28", "PC蛋蛋", "庄家", "买大小",
    ],
    "porn": [
        "卖淫", "包夜", "约炮", "援交", "上门服务", "成人视频", "色情",
        "AV女优", "性服务", "嫖娼", "做鸡",
    ],
    "fraud": [
        "杀猪盘", "投资骗", "假冒身份", "虚假中奖", "钓鱼链接", "诈骗",
        "假发货", "刷单返利", "兼职刷单",
    ],
    "mlm": [
        "传销", "拉人头", "三级分销", "层级返佣", "资金盘", "MLM",
        "无限代", "金字塔", "拉下线",
    ],
    "illegal_finance": [
        "非法集资", "高利贷", "配资", "虚拟币传销", "ICO 推广",
        "杠杆配资", "民间借贷",
    ],
    "medical": [
        "确诊", "处方", "药方", "治愈", "包治", "祖传秘方", "替代医生",
        "中医诊断", "癌症治愈",
    ],
    "finance_tip": [
        "保证收益", "稳赚不赔", "内幕消息", "私荐股", "操纵股价",
        "黑马股", "涨停板预测",
    ],
    "fake_promotion": [
        "三无产品", "假货代购", "高仿", "A货",
    ],
    "political": [
        "颠覆国家", "反动言论", "极端宗教",
    ],
}


@dataclass
class ComplianceHit:
    category: str          # 命中类别
    keywords: list[str]    # 命中关键词
    severity: str          # high/medium/low（高=立即拒绝 · 低=审核）

    @property
    def reason(self) -> str:
        return f"{self.category}: 命中 [{', '.join(self.keywords[:3])}]"


# 类别严重度
SEVERITY_MAP = {
    "gambling": "high",
    "porn": "high",
    "fraud": "high",
    "mlm": "high",
    "illegal_finance": "high",
    "political": "high",
    "medical": "medium",        # 需人审 · 可能正常医美咨询
    "finance_tip": "medium",    # 需人审 · 可能正常理财咨询
    "fake_promotion": "medium",
}


def detect_gray_intent(text: str) -> Optional[ComplianceHit]:
    """检测文本是否含灰产关键词。返回首个命中（按字典顺序）。"""
    if not text or not text.strip():
        return None

    text_lower = text.lower()
    for category, keywords in GRAY_KEYWORDS.items():
        hits = [kw for kw in keywords if kw.lower() in text_lower]
        if hits:
            return ComplianceHit(
                category=category,
                keywords=hits,
                severity=SEVERITY_MAP.get(category, "medium"),
            )
    return None


def detect_all(text: str) -> list[ComplianceHit]:
    """返回所有命中类别（用于审计 · 不仅首个）。"""
    if not text or not text.strip():
        return []
    text_lower = text.lower()
    out: list[ComplianceHit] = []
    for category, keywords in GRAY_KEYWORDS.items():
        hits = [kw for kw in keywords if kw.lower() in text_lower]
        if hits:
            out.append(ComplianceHit(
                category=category,
                keywords=hits,
                severity=SEVERITY_MAP.get(category, "medium"),
            ))
    return out


def is_blocked(text: str) -> bool:
    """快速判断 · 是否应拒绝处理（high severity 即拒绝）。"""
    hit = detect_gray_intent(text)
    return hit is not None and hit.severity == "high"


def get_rejection_reply(hit: ComplianceHit) -> str:
    """生成给客户的拒绝回复（不暴露我们识别的关键词 · 礼貌）。"""
    return "抱歉 · 这个话题不在我们服务范围内。如有其他问题欢迎咨询~"
