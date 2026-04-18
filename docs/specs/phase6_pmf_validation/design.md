# Phase 6 · PMF 验证 · Design

---

## 1. landing 页架构

```
public/
├── index.html         # 主页
├── product.html       # 产品介绍
├── pricing.html       # 定价
├── faq.html           # 常见问题
├── privacy.html       # 隐私政策
├── terms.html         # 用户协议
├── assets/
│   ├── logo.svg
│   ├── demo.mp4       # 60s 演示
│   └── screenshots/
└── styles.css
```

技术栈：纯 HTML + CSS + 极少 JS（不上 React，太重）。

---

## 2. 主页文案骨架

```
[Hero] AI 数字分身 · 让你的微信回复像你自己 · 24h 在线 · 0 漏单

[痛点 3 列]
  · 半夜客户问 → 错过最佳成交时机
  · 多个微信账号 → 顾此失彼
  · 手打回复累 → 灵感枯竭

[解决方案]
  白羊 = 你的 AI 副驾驶
  · 学你说话风格（专属 LoRA · 用 3 个月越来越像你）
  · 一键采纳（默认不自动发 · 你按发送键才发）
  · 反封号设计（日配额 + 7 天去重 + 工作时间）

[效果对比]
  使用前：每天回复 50 条 · 漏单 30%
  使用后：每天回复 100 条 · 漏单 5%

[内测申请]
  限 10 名 · ¥199 定金锁名额（30 天内全额抵扣）
  [立即报名]

[FAQ]
  Q1: 会被封号吗？
  Q2: 我的聊天记录安全吗？
  Q3: AI 真的能学会我的风格吗？
  ...

[最后 CTA]
  现在不上车，6 个月后追不上同行
```

---

## 3. 小红书 3 篇内容

```
篇 1: AI 创业日记 Day X · 我是怎么用 AI 一个人做 SaaS 的
  · 立项故事
  · 8 周路线
  · 第一个客户

篇 2: 微商朋友的真实痛点 · 我做 AI 助手是为了解决这 5 件事
  · 漏单
  · 重复
  · 半夜
  · 多号
  · 累

篇 3: 演示 · AI 学了我 30 天的聊天记录后...
  · 截图对比
  · "你看，分不清哪句是我说的"
  · 下面留言区报名
```

---

## 4. 抖音 60s 脚本

```
0-5s [钩子]
   "做微商最怕什么？"
   "凌晨 3 点客户问 '在么' 你没看到"

5-15s [问题]
   屏幕展示：客户消息红点 99+
   "一天 500 条消息 · 一个人怎么回？"

15-35s [方案]
   展示白羊浮窗 · AI 生成回复 · 一键采纳
   "AI 学你说话风格 · 你只要按发送键"

35-55s [效果]
   "试用 30 天 · 我的成交率涨了 3 倍"
   截图：聊天 + 收款

55-60s [CTA]
   "评论区留言获取试用资格 · 限 10 名"
```

---

## 5. 早鸟 ¥199 定金机制

```python
# server/early_bird.py（占位）
class EarlyBirdManager:
    """前 10 名 ¥199 定金 · 30 天后转正抵扣全部安装费 ¥1980。"""

    async def reserve_slot(self, contact_info: dict, paid_amount: int) -> dict:
        if paid_amount != 19900:  # 199 元
            raise ValueError("amount must be 19900 cents")
        slot_no = await self._next_slot()
        if slot_no > 10:
            raise ValueError("早鸟名额已满")
        # 创建 tenant_pending · 30 天试用 · 待转正
        ...

    async def convert(self, slot_no: int) -> dict:
        # 转正：补 ¥1781（¥1980 - ¥199）+ ¥299 首月
        ...

    async def refund(self, slot_no: int) -> dict:
        # 7 天无理由全额退
        ...
```
