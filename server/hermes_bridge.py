"""[DEPRECATED · BACKWARD-COMPAT ALIAS]

本文件原是 wechat_agent 与 whale_tracker 项目 hermes-agent 的桥接层。
2026-04-16 First Wave 重构后 · 实现已经搬到 `server/llm_client.py` · 类名 `LLMClient`。

新代码请直接：
    from server.llm_client import LLMClient

本文件仅保留 alias 用于已有测试的向后兼容 · 后续会彻底删除。
"""

from server.llm_client import LLMClient

# 向后兼容别名 · 旧测试用 HermesBridge 仍能工作
HermesBridge = LLMClient

__all__ = ["HermesBridge", "LLMClient"]
