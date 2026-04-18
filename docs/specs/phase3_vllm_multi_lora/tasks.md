# Phase 3 · vLLM 多 LoRA · Tasks

- [ ] `server/lora_registry.py` LoRA 扫描注册
- [ ] `server/vllm_client.py` openai-python 调 vLLM
- [ ] `server/canary.py` 灰度控制器
- [ ] `server/model_router.py` 增强 · 接 vllm 路由
- [ ] `client/qt6_popup.py` Qt6 浮窗
- [ ] `scripts/vllm_systemd.service` systemd 部署
- [ ] `scripts/launch_vllm.sh` 启动脚本
- [ ] `tests/test_lora_registry.py`
- [ ] `tests/test_canary.py`
- [ ] `tests/test_vllm_route_integration.py`
- [ ] CLI: `baiyang-deploy-lora` 命令
- [ ] Phase 3 验证：5 LoRA 模拟部署 + 灰度跑通

完成定义：测试 ≥ 8 用例，灰度算法验证 promote/rollback 阈值正确。
