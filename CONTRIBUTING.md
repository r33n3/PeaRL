# Contributing to PeaRL

## Development Setup

```bash
git clone https://github.com/your-org/pearl
cd pearl
pip install -e ".[dev]"
docker compose up -d postgres redis minio
```

Run the API in local mode (SQLite, no external services needed for most work):

```bash
PEARL_LOCAL=1 uvicorn pearl.main:app --reload --port 8081
```

Run tests:

```bash
PEARL_LOCAL=1 pytest tests/ -q
```

## Branch Naming

- `feat/short-description` — new features
- `fix/short-description` — bug fixes
- `chore/short-description` — maintenance, deps, CI
- `docs/short-description` — documentation only
- `security/short-description` — security hardening

## PR Workflow

1. Branch from `main`
2. Write code + tests
3. Run `ruff check src/ tests/` and fix any lint errors
4. Run `PEARL_LOCAL=1 pytest tests/ -q` — all tests must pass
5. Open a PR against `main`
6. CI runs lint + test + build + contract jobs automatically
7. At least one review required before merge

## Test Requirements

- New routes must have at least one contract test in `tests/contract/`
- New workers must have unit tests verifying job lifecycle
- New ORM models must be included in the `tests/conftest.py` fixture teardown
- New MCP tools require updating the tool count assertion in `tests/test_mcp.py`

## Code Style

- Python 3.12+ type hints everywhere
- `ruff` for linting (line length 100, target py312)
- Async all the way — no `asyncio.run()` inside async code
- Use `structlog` for logging in route handlers and workers
- Use stdlib `logging.getLogger(__name__)` in middleware and exception handlers (where structlog isn't configured yet at import time)
- Return plain dicts from routes — no Pydantic model serialization in route handlers

## Architecture Conventions

See [`docs/architecture.md`](docs/architecture.md) for the full picture. Key rules:

- **Repository pattern** — all DB access via `src/pearl/repositories/`. No raw SQL in routes.
- **Worker pattern** — extend `BaseWorker`, register in `src/pearl/workers/registry.py`
- **Error handling** — use custom exceptions from `src/pearl/errors/exceptions.py` (`NotFoundError`, `ValidationError`, `AuthorizationError`, etc.)
- **ID prefixes** — every entity uses a `generate_id(prefix)` call. See `CLAUDE.md` for the full prefix table.
- **Governance gates** — endpoints that decide approvals or exceptions must use `Depends(RequireReviewer)`. Do not add reviewer-level access to the `PEARL_LOCAL=1` role.

## Security Guidelines

### Governance Endpoints

Any new endpoint that approves, rejects, or modifies governance records (approvals, exceptions, false-positive findings) **must** use `Depends(RequireReviewer)`. This is a hard control against autonomous agent governance bypass.

### Logging Sensitive Actions

All `AuthorizationError` raises are automatically logged as `governance_access_denied` by the exception handler. For other security-relevant events (e.g., rate limit exceeded, invalid token patterns), add a structured log with a consistent event name so SIEM queries can aggregate them.

### Bash Guard Hook

If you work on this repo with Claude Code, install the governance bypass guard:

```bash
# Test it works:
echo '{"tool_input":{"command":"curl -X POST http://localhost:8081/api/v1/approvals/appr_test/decide"}}' \
  | python3 scripts/pearl_bash_guard.py
# Expected: exit 2, blocked message
```

See [`docs/security_research/SECURITY_HARDENING.md`](docs/security_research/SECURITY_HARDENING.md) for installation instructions.

## Commit Messages

Use imperative present tense: "Add scanner worker" not "Added scanner worker".

Format:
```
<type>: <short summary>

<optional body>
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`, `security`

## Release Process

1. Tag a version: `git tag v1.2.0`
2. Push tag: `git push origin v1.2.0`
3. GitHub Actions release workflow builds and pushes Docker image to GHCR
4. Create GitHub Release with generated notes
