# Phase 2 · LoRA 训练管线 · Tasks

> Spec ID：`phase2_lora_training`
> 任务粒度：每条 1-3 小时

---

## P0 · 数据采集

- [ ] `pipeline/extract_chat.py` 真实集成 WeChatMsg sqlite 解析
- [ ] `pipeline/pair_messages.py` 配对算法（5 分钟窗口）
- [ ] `pipeline/desensitize.py` 去敏（手机/卡号/身份证/邮箱/链接）
- [ ] `pipeline/filter.py` 噪音过滤（长度/纯标点/叠字）
- [ ] `tests/test_extract_chat.py` 配对算法测试
- [ ] `tests/test_desensitize.py` 去敏测试

## P1 · 数据格式

- [ ] `pipeline/format.py` ChatML / Alpaca 转换
- [ ] `tests/test_format.py` 格式 round-trip

## P2 · 训练启动

- [ ] `pipeline/train_lora.py` LLaMA-Factory yaml 完整生成器
- [ ] `pipeline/launcher.py` subprocess 启动 + log 流式
- [ ] `pipeline/early_stop.py` loss 不降早停
- [ ] `pipeline/oom_fallback.py` OOM 自动降配
- [ ] `tests/test_train_config.py` yaml 正确性

## P3 · 评估

- [ ] `pipeline/judge.py` judge LLM 接口（hermes_bridge 调 DeepSeek-R1）
- [ ] `pipeline/eval_report.py` markdown 报告生成
- [ ] `tests/test_judge.py` mock LLM 解析

## P4 · DPO

- [ ] `pipeline/dpo_pair.py` 增强（按 review.decision 智能配对）
- [ ] `pipeline/dpo_train.py` DPO 启动器
- [ ] `tests/test_dpo_pair.py` 配对算法

## P5 · 部署整合

- [ ] `pipeline/register_lora.py` 训完写入 model_router
- [ ] `server/model_router.py` 增强（从 disk 自动发现 LoRA）
- [ ] `tests/test_register_lora.py`

## P6 · CLI

- [ ] `pipeline/cli.py` `baiyang-train --tenant XXX --src wxmsg.db`
- [ ] `tests/test_cli_smoke.py`

## P7 · 文档

- [ ] `docs/lora_training_guide.md` 给连大哥的训练操作手册
- [ ] `pipeline/README.md`

## P8 · 验证

- [ ] `pytest tests/test_pipeline*` 全绿（≥ 12 用例）
- [ ] mini smoke train（5 条数据 1 epoch）
- [ ] 评估报告生成 markdown

---

## 完成定义

- 所有 `[ ]` 变 `[x]` 或 `[s]`
- 测试 ≥ 12 个 case
- mock 模式 macOS 跑通完整管线
- 真训练等 GPU 机器（连大哥决定云 / 本地）
- 文档让连大哥能独立跑 `baiyang-train --tenant tenant_0001 --src wxmsg.db`
