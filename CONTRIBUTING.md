# Contributing to PeaRL

## Development Setup

```bash
git clone https://github.com/your-org/pearl
cd pearl
pip install -e ".[dev]"
docker compose up -d postgres redis minio
```

## Branch Naming

- `feat/short-description` — new features
- `fix/short-description` — bug fixes
- `chore/short-description` — maintenance, deps, CI
- `docs/short-description` — documentation only

## PR Workflow

1. Branch from `main`
2. Write code + tests
3. Run `ruff check src/ tests/` and fix any lint errors
4. Run `PEARL_LOCAL=1 pytest tests/ -v` — all tests must pass
5. Open a PR against `main`
6. CI runs lint + test + build + contract jobs automatically
7. At least one review required before merge

## Test Requirements

- New routes must have at least one contract test in `tests/contract/`
- New workers must have unit tests verifying job lifecycle
- New ORM models must be included in the `tests/conftest.py` fixture teardown

## Code Style

- Python 3.12+ type hints everywhere
- `ruff` for linting (line length 100, target py312)
- Async all the way — no `asyncio.run()` inside async code
- Use `structlog` for logging, not `print()` or stdlib `logging` directly

## Commit Messages

Use imperative present tense: "Add scanner worker" not "Added scanner worker".

Format:
```
<type>: <short summary>

<optional body>
```

Types: `feat`, `fix`, `chore`, `docs`, `test`, `refactor`

## Release Process

1. Tag a version: `git tag v1.2.0`
2. Push tag: `git push origin v1.2.0`
3. GitHub Actions release workflow builds and pushes Docker image to GHCR
4. Create GitHub Release with generated notes
