# Phase 7 · 放大 · Design

---

## 1. 客服 SOP

```
分级 1：FAQ 自动回复（AI 客服）
   - "怎么装？" → 给 SETUP.md 链接 + 视频
   - "封号怎么办？" → 给 RISK_CONTROL.md
   - "续费？" → 给 dashboard 链接

分级 2：人工兼职（学生 ¥3-5K/月）
   - 群里 5 分钟内响应
   - 复杂问题转给童虎/连大哥

分级 3：连大哥亲自
   - 退款投诉
   - 大客户（旗舰版）
   - 法律相关
```

---

## 2. 行业飞轮 Layer 4

```python
# evolution/industry_flywheel.py
class IndustryFlywheel:
    """匿名聚合所有客户的成交话术 → 提取 Top 50 模式。"""

    async def extract_patterns(self, industry: str = "微商", min_acceptance: float = 0.8) -> list[dict]:
        async with session_scope() as s:
            # 1. 拿所有 industry 客户的 high-acceptance 回复
            rows = (await s.execute(
                select(Suggestion, Review).join(Review, Review.msg_id == Suggestion.msg_id)
                .where(Review.decision == "accept")
                .limit(10000)
            )).all()

        # 2. 差分隐私脱敏
        dp_processed = self._diff_privacy(rows)

        # 3. 模式提取（embedding cluster + LLM 总结）
        patterns = await self._cluster_patterns(dp_processed)

        # 4. Top 50 模式生成新 prompt
        return patterns[:50]

    @staticmethod
    def _diff_privacy(rows):
        # ε-差分隐私 · 添加 noise · 去 PII
        ...
```

---

## 3. 转介绍机制

```python
# server/referral.py
class ReferralManager:
    async def create_code(self, tenant_id: str) -> str:
        # 生成 6 位邀请码
        ...
    async def claim_reward(self, referrer: str, new_tenant: str, paid_amount: int) -> int:
        # 拉一个返 ¥200 现金（或 1 个月免费）
        ...
```

---

## 4. SLA 监控

```yaml
# monitoring/sla.yaml
metrics:
  - name: client_uptime
    target: 99%
  - name: server_p99_latency
    target: < 2s
  - name: lora_inference_p95
    target: < 1.5s
  - name: customer_response_first_minute
    target: > 90%
  - name:封号率
    target: 0
```
