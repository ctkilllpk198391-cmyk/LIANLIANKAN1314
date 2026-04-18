# Phase 5 · 商业化闭环 · Requirements

> Spec ID：`phase5_commercialization`
> 阶段：Phase 5（task_plan.md Week 5 Day 29-35）

---

## 1. 功能范围

5 个种子客户跑起来，数据回流，第一个付费链路完整。

### 1.1 子模块
1. **微信支付商户接入**：JSAPI / Native 支付
2. **订阅生命周期**：trial / pro / flagship · 月费 + 安装费
3. **客户 Dashboard**：采纳率/成交/涨粉/订单
4. **法务三件套**：用户协议 / 隐私政策 / 免责声明（法务定稿）
5. **种子客户工具**：批量部署 + 配置 + 监控

---

## 2. 验收

### 2.1 支付
- [ ] 微信支付商户号开通（连大哥线下）
- [ ] `server/billing.py` 订阅创建/查询/取消
- [ ] 支付成功 webhook 接入 → 自动激活 tenant
- [ ] 退款流程接入

### 2.2 订阅
- [ ] 三档自动切换（trial → pro → flagship）
- [ ] 到期自动降级 trial 或停用
- [ ] 续费提醒（到期前 7 天 + 1 天）
- [ ] 订阅历史可查

### 2.3 Dashboard
- [ ] `/v1/dashboard/{tenant_id}` 返回 JSON 看板数据
  - 今日采纳率、采纳数、拒绝数、编辑率
  - 本周成交（如果接 CRM）
  - 月度增长曲线
  - LoRA 训练状态
  - 配额使用率
- [ ] 简单 HTML 模板（Phase 6 升 Web 应用）

### 2.4 法务
- [ ] `legal/user_agreement.md` 法务正式签字版
- [ ] `legal/privacy_policy.md` 同上
- [ ] `legal/disclaimer.md` 同上
- [ ] 客户安装时强制阅读 + 勾选

### 2.5 种子客户
- [ ] 5 个种子客户名单（连大哥线下）
- [ ] 远程部署脚本 + 远程指导清单
- [ ] 反馈收集表 · 每周 1 次电话回访
