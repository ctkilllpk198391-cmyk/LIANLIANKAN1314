"""F3 · embedder + cosine 测试。"""

from __future__ import annotations

import os

from server.embedder import (
    EMBEDDING_DIM,
    BGEEmbedder,
    cosine,
    get_default_embedder,
    reset_default_embedder,
)


def test_mock_embedder_deterministic():
    """同样文本 → 同样向量。"""
    e = BGEEmbedder(mock=True)
    v1 = e.encode("产品价格 99 元")
    v2 = e.encode("产品价格 99 元")
    assert v1 == v2
    assert len(v1) == EMBEDDING_DIM


def test_mock_embedder_different_text():
    e = BGEEmbedder(mock=True)
    v1 = e.encode("产品价格 99")
    v2 = e.encode("完全不同的句子")
    assert v1 != v2


def test_mock_embedder_normalized():
    e = BGEEmbedder(mock=True)
    v = e.encode("test")
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 1e-6


def test_mock_embedder_empty_text():
    e = BGEEmbedder(mock=True)
    v = e.encode("")
    assert len(v) == EMBEDDING_DIM
    assert all(x == 0.0 for x in v)


def test_encode_batch():
    e = BGEEmbedder(mock=True)
    vs = e.encode_batch(["a", "b", "c"])
    assert len(vs) == 3
    assert all(len(v) == EMBEDDING_DIM for v in vs)


def test_cosine_identical():
    v = [0.1, 0.2, 0.3, 0.4]
    assert abs(cosine(v, v) - 1.0) < 1e-6


def test_cosine_orthogonal():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(cosine(a, b)) < 1e-6


def test_cosine_empty():
    assert cosine([], [1.0]) == 0.0
    assert cosine([1.0, 2.0], []) == 0.0


def test_default_embedder_via_env(monkeypatch):
    monkeypatch.setenv("BAIYANG_EMBEDDER_MOCK", "true")
    reset_default_embedder()
    e = get_default_embedder()
    assert e.mock is True
    reset_default_embedder()
