"""Wave 12 · 拟真引擎规则源 (server 侧).

纯配置中心 · 不依赖数据库。客户端通过 GET /v1/wcf/rules/{tenant_id} 拉取。

6 维拟真规则:
1. 作息 circadian     — 凌晨/午休静默 · 活跃时段区分
2. 延迟分布 latency   — 指数分布 λ=1/8 基准 · clip [3, 60] 秒
3. 输入速度 typing    — 80-120 字/分 · 长消息分段 · "输入中..." 假状态
4. 硬节流 rate_limit  — 只留安全档(每号每天主动 20 + 回复 50 + 加好友 5 + 朋友圈 1)
5. 行为噪声 noise     — 5% 回删 · 10% 先输"嗯" · 3% 假查朋友圈
6. 封号征兆 kill_switch — 失败率 >5% 冷却 30min · 系统风控消息 24h 静默

Wave 12 只有 "安全档" (safe) · 标准/激进档已砍。
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field


class CircadianRules(BaseModel):
    """作息窗口 · 每个元组是 (start_hour, end_hour) 24h 制 · start 含 end 不含。"""
    silent: List[Tuple[int, int]] = Field(default_factory=lambda: [(0, 7), (12, 14)])
    ramp_up: List[Tuple[int, int]] = Field(default_factory=lambda: [(7, 9)])
    peak: List[Tuple[int, int]] = Field(default_factory=lambda: [(9, 12), (14, 22)])
    wind_down: List[Tuple[int, int]] = Field(default_factory=lambda: [(22, 24)])
    latency_multiplier: Dict[str, float] = Field(default_factory=lambda: {
        "silent": 0.0,      # 0 = 入队不发
        "ramp_up": 2.0,
        "peak": 1.0,
        "wind_down": 1.5,
    })


class LatencyRules(BaseModel):
    """回复延迟指数分布参数 · Wave 13 调到 5-10s 体验档。"""
    exp_lambda_base: float = 1 / 3      # 均值 3s · 大多落 5-8s
    exp_lambda_peak: float = 1 / 2      # 高峰更快
    exp_lambda_night: float = 1 / 5     # 夜间稍慢
    clip_min: float = 5.0
    clip_max: float = 10.0


class TypingRules(BaseModel):
    """模拟键盘输入速度。"""
    char_delay_ms: Tuple[int, int] = (500, 800)  # 每字符延迟范围 · 80-120 字/分
    long_msg_split_threshold: int = 50           # >50 字消息分段
    long_msg_split_pause_sec: Tuple[int, int] = (2, 5)
    show_typing_sec: Tuple[int, int] = (2, 5)    # "对方正在输入中..." 持续


class RateLimitRules(BaseModel):
    """硬节流 · 安全档。"""
    daily_active_send: int = 20      # 主动发起(不是回复)
    daily_reply: int = 50            # 回复客户
    daily_friend_add: int = 5        # 加好友
    daily_moments: int = 1           # 朋友圈发布
    daily_group_msg: int = 3         # 群消息
    hourly_msg: int = 10             # 每小时上限
    min_interval_sec: int = 30       # 最小消息间隔
    same_template_daily_max: int = 2 # 同模板每天最多 2 次


class NoiseRules(BaseModel):
    """行为噪声 · 让 AI 看起来像真人。"""
    typo_delete_prob: float = 0.05
    prefix_filler_prob: float = 0.10      # 先输 "嗯 / 稍等" 再发正文
    prefix_filler_words: List[str] = Field(default_factory=lambda: [
        "嗯", "稍等", "稍等哈", "嗯嗯", "好的", "哦", "让我看看", "等下"
    ])
    fake_moment_view_prob: float = 0.03   # 3% 触发假"查朋友圈"


class KillSwitchRules(BaseModel):
    """封号征兆秒停。"""
    send_fail_rate_threshold: float = 0.05   # 5% 失败率触发
    send_fail_window_sec: int = 300          # 5 分钟滑窗
    cooldown_sec: int = 1800                 # 冷却 30 分钟
    hook_fail_consecutive: int = 3           # 连续 3 次 hook 失败
    risk_msg_silence_sec: int = 86400        # 收到系统风控消息 → 24h 静默
    risk_keywords: List[str] = Field(default_factory=lambda: [
        "账号异常", "限制登录", "被举报", "涉嫌违规", "暂时无法", "冻结",
        "请进行安全验证", "安全提示", "为了你的账号安全",
    ])


class WcfRules(BaseModel):
    """下发给客户端的完整规则 JSON."""
    version: int = 1
    tier: str = "safe"   # 安全档 · Wave 12 唯一支持
    circadian: CircadianRules = Field(default_factory=CircadianRules)
    latency: LatencyRules = Field(default_factory=LatencyRules)
    typing: TypingRules = Field(default_factory=TypingRules)
    rate_limit: RateLimitRules = Field(default_factory=RateLimitRules)
    noise: NoiseRules = Field(default_factory=NoiseRules)
    kill_switch: KillSwitchRules = Field(default_factory=KillSwitchRules)


# ─── 默认规则(安全档 · 所有 tenant 共用) ────────────────────────────────────

DEFAULT_RULES = WcfRules()


def get_rules_for_tenant(tenant_id: str) -> WcfRules:
    """Wave 12: 所有 tenant 同一套安全档规则。

    后续可按 tenant 灰度 / 按订单金额 / 按账号健康度动态调整。
    """
    _ = tenant_id  # 占位 · 未来按 tenant 差异化
    return DEFAULT_RULES


def dump_default_rules() -> Dict[str, Any]:
    """导出默认规则字典(测试 + 调试用)。"""
    return DEFAULT_RULES.model_dump()
