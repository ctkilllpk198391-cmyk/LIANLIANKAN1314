# 成本经济学 · API vs 自部署 · 三阶段路径

> 2026-04-15 决策 · 给一人公司 · 微商场景
> 数据来源：DeepSeek/GLM/Claude 2026 Q2 实测价格 + vLLM 实测吞吐

---

## 一、单条消息成本表

假设：客户日均 100 条 · 月 3000 条 · 单条 input 500 tok / output 100 tok

| 模型 | 价格（输入/输出 $/MTok）| 单条 ¥ | 月/客户 |
|---|---|---|---|
| **DeepSeek V3.2** | $0.28 / $0.42 | ¥0.0013 | ¥3.9 |
| **GLM-5.1** | $0.95 / $3.15 | ¥0.0057 | ¥17（全场景）/ ¥1.7（10%）|
| Claude Sonnet 4.6 | $3.00 / $15.0 | ¥0.0294 | ¥88 |
| Qwen3-Max API | 按阿里百炼 | 类似 GLM | — |
| **自部署 Qwen3-30B-A3B** | A100 ¥10K/月 ÷ 100 客户 | — | **¥100** |

---

## 二、Hybrid 路由 v3（按 intent · 拟人优先）

| 占比 | intent | 走哪 | 单价 ($/MTok) | 月/客户 |
|---|---|---|---|---|
| 60% 闲聊/砍价/共情 | greeting/chitchat/negotiation | **Doubao 1.5 Pro** ⭐ | ~$0.5/$1.0 | ¥6 |
| 25% 询价/订单 | inquiry/order | **DeepSeek V3.2** | $0.28/$0.42 | ¥1 |
| 10% 高风险 | complaint/sensitive | **GLM-5.1** | $0.95/$3.15 | ¥1.7 |
| 5% 角色调侃 | 创意场景 | **MiniMax abab 6.5s** | $0.14/$0.14（¥1/MTok）| ¥0.3 |
| **合计** | — | — | — | **~¥9 / 月 / 客户** |

**vs 之前 v2（全 DeepSeek）**：
- v2: ¥6 / 月 · 通用回复 70% 像
- v3: ¥9 / 月 · 拟人回复 85% 像（升 50% 成本换 15% 拟人度）
- 第一个付费客户回本 = 一周（¥699 月费 vs ¥9 成本 = 77 倍 ROI）

---

## 三、盈亏平衡

- API 月成本：¥6 / 客户
- 自部署月固定：¥10K（1 张 A100 80G）
- **平衡点：1700 客户**

---

## 四、三阶段路径（最优）

### Phase 1-6（PMF · 0-10 客户）
- **全 API · 不训 LoRA**（用通用 LLM + 老板 style hint）
- GPU 投入：**¥0**
- 月总成本：**¥60**（10 客户 × ¥6）
- 风险：差异化弱 · 但能验证 "客户愿不愿付钱"

### Phase 7（放大 · 10-100 客户）
- 选择性训 LoRA（autodl 4090 按时 ¥2/小时 · 训完关）
- 推理仍主走 API（保留 30% LoRA 推理 → 推理 GPU 按需开）
- 月总成本：¥1K-3K
- 收益：高 LTV 客户开始用专属分身

### Phase 8（规模 · 100-1000 客户）
- 自买 / 包月 A100 80G ¥10K
- 70% 自部署 LoRA · 30% API 兜底
- 月总成本：¥10K-30K
- 毛利率 80%+

### Phase 9（独角兽 · 1000+）
- 多 GPU 集群 · vLLM/SGLang
- API 仅作 fallback（< 5%）
- 月总成本规模化 · 单客户 < ¥10

---

## 五、关键约束

**API 不能挂客户专属 LoRA**（DeepSeek/GLM/Claude 都不开放）
→ 想要"专属分身"必须自部署
→ 但自部署月固定成本高

**所以正确的策略是阶段化**：
- 早期（无客户证明 PMF）→ 全 API + 通用 LLM + style hint = 90% 像
- 中期（客户付费要差异化）→ 自部署 + LoRA = 95% 像
- 晚期（规模摊销）→ 自部署成本最优

---

## 六、API key 申请清单

### DeepSeek（必申）
- https://platform.deepseek.com/api_keys
- 注册即送 ¥10 · 够测 1 周
- 充值最小 ¥10 起 · 按量计费

### 智谱 GLM（必申）
- https://bigmodel.cn/usercenter/apikeys
- 注册即送 ¥18 · 够测 1 周
- 国产合规 · 推荐做高风险路由

### Anthropic Claude（可选 · 国际客户用）
- https://console.anthropic.com/
- 需要海外信用卡 / 虚拟卡

---

## 七、给连大哥的执行清单

1. **今天**：申请 DeepSeek + GLM API key（30 分钟）
2. **明天**：填到 `.env` · 切 `BAIYANG_HERMES_MOCK=false` · 真跑一次
3. **本周**：用自己微信账号当 0 号客户 · 真用 7 天看效果
4. **下周**：第一个朋友试用 · 看采纳率 ≥ 50% 才扩大

**月预算**（建议）：
- API：¥100 / 月（覆盖你 + 5 个朋友试用）
- 服务器（不含 GPU）：¥200 / 月
- 域名：¥5 / 月（年付 ¥55）
- **合计 ¥300 / 月** · 第一个付费客户 ¥1980 + ¥299 一个月就回本

---

## 八、相关 ADR

- 决策：**Phase 1-6 不训 LoRA · 全 API**
- 替代方案：早期就自部署 + 训 LoRA → 否决（GPU 月固定 ¥10K · 10 个客户均摊太重）
- 将来重新评估：客户达 50 时 · 看续费率 + 老板风格诉求

---

## 来源

- DeepSeek API Pricing 2026: https://benchlm.ai/blog/posts/deepseek-api-pricing
- GLM-5.1 Pricing: https://bigmodel.cn/pricing
- Anthropic API: https://www.anthropic.com/pricing
- vLLM Multi-LoRA Production: https://www.spheron.network/blog/vllm-vs-tensorrt-llm-vs-sglang-benchmarks/
- Qwen3 8 模型: https://36kr.com/p/3271032585609346
