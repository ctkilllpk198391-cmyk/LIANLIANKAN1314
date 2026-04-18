"""配置加载 · 合并 yaml + .env。"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_env(key: str, default: str | None = None) -> str | None:
    return os.getenv(key, default)


def merge_config(yaml_path: Path) -> dict[str, Any]:
    """yaml + env 合并，env 优先级更高。"""
    cfg = load_yaml(yaml_path)

    # env 覆盖
    if val := get_env("BAIYANG_DB_URL"):
        cfg.setdefault("database", {})["url"] = val
    if val := get_env("BAIYANG_HERMES_URL"):
        cfg.setdefault("hermes", {})["base_url"] = val
    if val := get_env("BAIYANG_HERMES_MOCK"):
        cfg.setdefault("hermes", {})["mock"] = val.lower() == "true"
    if val := get_env("BAIYANG_CLASSIFIER"):
        cfg.setdefault("llm", {})["classifier_mode"] = val

    return cfg
