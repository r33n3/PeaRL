.PHONY: help dev-up dev-down test test-fast lint fmt typecheck migrate shell logs clean token

help:
	@echo "PeaRL — development commands"
	@echo ""
	@echo "  make dev-up        Start the full stack (API, Postgres, Redis, frontend)"
	@echo "  make dev-down      Stop and remove containers"
	@echo "  make test          Run full test suite (SQLite, no Docker needed)"
	@echo "  make test-fast     Run tests skipping slow integration tests"
	@echo "  make lint          Run ruff linter"
	@echo "  make fmt           Auto-format with ruff"
	@echo "  make typecheck     Run mypy type checks"
	@echo "  make migrate       Apply Alembic migrations against Docker stack"
	@echo "  make shell         Open a Python shell with PeaRL app context"
	@echo "  make logs          Tail pearl-api logs"
	@echo "  make token         Generate a 30-day MCP service token"
	@echo "  make clean         Remove __pycache__, .pytest_cache, build artefacts"

# ── Docker stack ────────────────────────────────────────────────────────────

dev-up:
	docker compose up -d --build
	@echo "API:      http://localhost:8080/api/v1/health/ready"
	@echo "Frontend: http://localhost:5177"
	@echo "MCP:      http://localhost:8080/mcp"

dev-down:
	docker compose down

logs:
	docker compose logs -f pearl-api

# ── Testing ─────────────────────────────────────────────────────────────────

test:
	PEARL_LOCAL=1 uv run pytest tests/ -q --tb=short --ignore=tests/test_timeline.py

test-fast:
	PEARL_LOCAL=1 uv run pytest tests/ -q --tb=short --ignore=tests/test_timeline.py -x -m "not slow"

test-security:
	PEARL_LOCAL=1 uv run pytest tests/security/ -v --tb=short

# ── Code quality ─────────────────────────────────────────────────────────────

lint:
	uv run ruff check src/ tests/

fmt:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/

typecheck:
	uv run mypy src/pearl --ignore-missing-imports

# ── Database ─────────────────────────────────────────────────────────────────

migrate:
	docker compose exec pearl-api alembic upgrade head

# ── Dev utilities ─────────────────────────────────────────────────────────────

shell:
	PEARL_LOCAL=1 uv run python -c "from pearl.main import app; import asyncio; print('PeaRL app loaded')"

token:
	@ACCESS=$$(curl -sf -X POST http://localhost:8080/api/v1/auth/login \
		-H "Content-Type: application/json" \
		-d '{"email":"admin@pearl.dev","password":"PeaRL-admin-2026"}' \
		| python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"); \
	curl -sf -X POST http://localhost:8080/api/v1/auth/service-token \
		-H "Authorization: Bearer $$ACCESS" \
		| python3 -m json.tool

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean."
