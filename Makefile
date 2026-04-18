.PHONY: help install test test-cov lint fmt run init-db seed clean

PYTHON := python3.11
UV := uv

help:
	@echo "白羊 · wechat_agent · 开发命令"
	@echo "  make install   - uv venv + 装依赖"
	@echo "  make test      - pytest 全跑"
	@echo "  make test-cov  - pytest + 覆盖率"
	@echo "  make lint      - ruff 检查"
	@echo "  make fmt       - ruff 格式化"
	@echo "  make run       - 启动 server (port 8327)"
	@echo "  make init-db   - 初始化 SQLite + schema"
	@echo "  make seed      - 种子 tenant_0001 (连大哥)"
	@echo "  make clean     - 清缓存"

install:
	$(UV) venv --python=$(PYTHON)
	$(UV) pip install -e ".[dev]"

install-postgres:
	$(UV) pip install -e ".[postgres]"

install-train:
	$(UV) pip install -e ".[train]"

test:
	$(UV) run pytest tests/ -v

test-cov:
	$(UV) run pytest tests/ -v --cov=server --cov=client --cov=shared --cov-report=term-missing

lint:
	$(UV) run ruff check .

fmt:
	$(UV) run ruff format .

run:
	$(UV) run uvicorn server.main:app --host 0.0.0.0 --port 8327 --reload

init-db:
	$(UV) run python scripts/init_db.py

seed:
	$(UV) run python scripts/seed_tenant.py

clean:
	rm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache htmlcov .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
