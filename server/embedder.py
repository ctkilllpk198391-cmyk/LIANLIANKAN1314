"""F3 · BGE 文本向量化包装 · 含 mock fallback。

选型：BAAI/bge-small-zh-v1.5 · 384 维 · ~100MB · 中文 SOTA-tier
- 首次启动延迟下载到 ~/.cache/huggingface/
- macOS M4 Pro 推理 ~50ms/chunk
- mock 模式（无依赖）：用 hash 生成确定性伪 embedding · 仅测试用

环境变量：
  BAIYANG_EMBEDDER_MODEL  默认 BAAI/bge-small-zh-v1.5
  BAIYANG_EMBEDDER_MOCK   true → 用 hash 兜底 · 不下模型
"""

from __future__ import annotations

import hashlib
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 384  # bge-small-zh-v1.5


class BGEEmbedder:
    """sentence-transformers 包装 · 懒加载 + mock fallback。"""

    def __init__(self, model_name: Optional[str] = None, mock: Optional[bool] = None):
        self.model_name = model_name or os.getenv(
            "BAIYANG_EMBEDDER_MODEL", "BAAI/bge-small-zh-v1.5"
        )
        if mock is None:
            mock = os.getenv("BAIYANG_EMBEDDER_MOCK", "false").lower() == "true"
        self.mock = mock
        self._model = None

    def _load_model(self):
        if self._model is None and not self.mock:
            try:
                from sentence_transformers import SentenceTransformer
                logger.info("loading embedder model: %s", self.model_name)
                self._model = SentenceTransformer(self.model_name)
            except Exception as e:
                logger.warning("embedder load failed · fallback to mock: %s", e)
                self.mock = True
        return self._model

    def encode(self, text: str) -> list[float]:
        if self.mock:
            return _hash_embedding(text)
        model = self._load_model()
        if model is None:
            return _hash_embedding(text)
        vec = model.encode(text, normalize_embeddings=True)
        return vec.tolist() if hasattr(vec, "tolist") else list(vec)

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        if self.mock:
            return [_hash_embedding(t) for t in texts]
        model = self._load_model()
        if model is None:
            return [_hash_embedding(t) for t in texts]
        vecs = model.encode(texts, normalize_embeddings=True, batch_size=16)
        return [v.tolist() if hasattr(v, "tolist") else list(v) for v in vecs]


def _hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """确定性伪 embedding · text 相同 → vec 相同 · 仅 mock/测试使用。"""
    if not text:
        return [0.0] * dim
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    raw = [(b - 128) / 128.0 for b in digest]
    while len(raw) < dim:
        raw.extend(raw[:dim - len(raw)])
    vec = raw[:dim]
    norm = (sum(x * x for x in vec)) ** 0.5
    return [x / norm if norm > 0 else 0.0 for x in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """轻量 cosine（不依赖 numpy · 测试友好）。"""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


_default_embedder: Optional[BGEEmbedder] = None


def get_default_embedder() -> BGEEmbedder:
    global _default_embedder
    if _default_embedder is None:
        _default_embedder = BGEEmbedder()
    return _default_embedder


def reset_default_embedder() -> None:
    """测试用 · 重置 default · 让环境变量重新生效。"""
    global _default_embedder
    _default_embedder = None
