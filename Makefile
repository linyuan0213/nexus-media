.PHONY: help install dev test test-cov lint typecheck bandit safety security check run clean

help:
	@echo "Nexus Media Backend"
	@echo "  make install   安装依赖"
	@echo "  make dev       安装开发依赖"
	@echo "  make test      运行测试"
	@echo "  make test-cov  运行测试并生成覆盖率报告"
	@echo "  make lint      运行 ruff 代码检查"
	@echo "  make typecheck 运行 pyright 类型检查"
	@echo "  make bandit    运行 bandit 安全扫描"
	@echo "  make safety    运行 pip-audit 依赖漏洞扫描"
	@echo "  make security  运行 bandit + pip-audit"
	@echo "  make check     运行 lint + typecheck + test"
	@echo "  make run       启动开发服务器"
	@echo "  make clean     清理缓存文件"

install:
	uv sync

dev:
	uv sync --dev

test:
	uv run pytest tests/ -v

test-cov:
	uv run pytest tests/ -v --cov=src/app --cov=src/api --cov=src/log --cov-report=term-missing

lint:
	uv run ruff check .

typecheck:
	uv run pyright src/ tests/

bandit:
	uv run bandit -c pyproject.toml -r src/

safety:
	uv run pip-audit

security: bandit safety

check: lint typecheck test

run:
	NEXUS_MEDIA_CONFIG=./config/config.yaml uv run python run.py

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true
