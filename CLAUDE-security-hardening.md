# Task: Security Hardening — MCP validation, rate limit headers, allowance versioning, dep bumps (`security-hardening`)

> **Read the root CLAUDE.md first** — it contains project-wide conventions, stack details, and coding standards that apply here.

## What I'm here to do

Four targeted hardening items, none dependent on each other, all fully self-contained:

1. **MCP tool input validation** — add `maxLength`/`maxItems` to all 50 tool schemas, add per-call audit event (GAP-10)
2. **Rate limit response headers** — add `X-RateLimit-*` headers so clients can self-regulate
3. **Allowance profile versioning** — add `profile_version` to `AllowanceProfileRow`, record version in use on task packets
4. **Dependency bumps** — resolve Dependabot medium/low security alerts

These are code quality and defence-in-depth fixes. No new endpoints.

## Branch

`worktree-security-hardening` — branched from `main`

## Scope — files I should touch

### MCP Tool Validation (GAP-10)
- `src/pearl/mcp/tools.py` — For every tool `inputSchema.properties` entry:
  - Add `"maxLength": 512` to all `"type": "string"` properties that accept free text (`rationale`, `description`, `title`, `reason`, `notes`, `message`, `comment`, `details`, etc.)
  - Add `"maxItems": 100` to all `"type": "array"` properties
  - Add `"minLength": 1` to required string IDs (already have `pattern` constraints — leave those)
  - **Do NOT change** `pattern` constraints, `enum` constraints, or `required` fields
  - After schemas: add a helper that writes a `ClientAuditEventRow` on every tool invocation. Look at `src/pearl/api/routes/task_packets.py:264` for how `ClientAuditEventRow` is created inline. Add the same pattern to each MCP tool handler with `action="mcp_tool_call"`, `tool_name=<tool name>`, `actor` from the tool's `project_id` or input args.

### Rate Limit Headers
- `src/pearl/api/middleware/rate_limit.py` — After `setup_rate_limiter()`, add a response middleware that injects `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers. slowapi supports this via `app.add_middleware(SlowAPIMiddleware)` — check if that's already configured. If not, add a `BaseHTTPMiddleware` that reads `app.state.limiter` and appends headers.

### Allowance Profile Versioning
- `src/pearl/db/models/allowance_profile.py` — ADD `profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)`
- `src/pearl/api/routes/allowance_profiles.py` — PATCH endpoint should increment `profile_version` on every update
- `src/pearl/db/models/task_packet.py` — ADD `allowance_profile_version: Mapped[int | None] = mapped_column(Integer, nullable=True)` — records the version in effect when the task packet was claimed
- `src/pearl/api/routes/task_packets.py` — In the `/claim` endpoint, read `allowance_profile_id` from the task packet and store the current `profile_version` into `allowance_profile_version`
- Create Alembic migration `004_add_allowance_profile_versioning.py` in `src/pearl/db/migrations/versions/`

### Dependency Bumps
- `pyproject.toml` — bump:
  - `cryptography` to latest stable (Dependabot low alert)
  - `requests` to latest stable (Dependabot medium alert)
  - `Pygments` to latest stable (Dependabot low alert)
- `frontend/package.json` — bump `picomatch` (Dependabot 2× medium alerts on picomatch <2.3.1)
  - Check `frontend/package-lock.json` or run `npm audit` to identify which package pulls in old picomatch

## Out of scope — do NOT modify

- `src/pearl/api/routes/approvals.py` — owned by `server-audit-trail`
- `src/pearl/api/routes/exceptions.py` — owned by `server-audit-trail`
- `src/pearl/services/promotion/gate_evaluator.py` — owned by `server-audit-trail`
- `tests/contract/test_audit_trail.py` — owned by `security-validation`
- `tests/security/attack_chain/` — owned by `security-validation`

## Shared risk files — ADD only, do not overwrite

- `src/pearl/db/models/__init__.py` — no changes expected
- `src/pearl/api/router.py` — no changes expected
- `src/pearl/mcp/tools.py` — adding constraints to existing schemas only, no removals

## Acceptance criteria

- [ ] All 50 MCP tool `"type": "string"` free-text properties have `"maxLength": 512`
- [ ] All 50 MCP tool `"type": "array"` properties have `"maxItems": 100`
- [ ] MCP tool calls write a `ClientAuditEventRow` with `action="mcp_tool_call"` (GAP-10)
- [ ] `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` present in rate-limited responses
- [ ] `AllowanceProfileRow.profile_version` field exists (default 1)
- [ ] PATCH `/allowance-profiles/{id}` increments `profile_version`
- [ ] `TaskPacketRow.allowance_profile_version` field exists
- [ ] Claim endpoint records `allowance_profile_version` at time of claim
- [ ] Alembic migration `004_...` created
- [ ] `pyproject.toml` dep versions bumped for cryptography, requests, Pygments
- [ ] `PEARL_LOCAL=1 pytest tests/ -q` passes — tool count assertions may need updating if test_mcp.py checks schema property counts

## Caution: test_mcp.py tool count

`tests/test_mcp.py` and `tests/security/test_tool_description_safety.py` both assert the MCP tool count. Adding `maxLength`/`maxItems` to schemas does NOT change the tool count — only adding/removing whole tools changes it. You should be safe, but check both files if tests fail.

## Setup

```bash
uv sync --dev
cd frontend && npm install
```

## Suggested first steps

1. Read `src/pearl/mcp/tools.py` lines 1–100 — understand tool schema structure
2. Read `src/pearl/api/routes/task_packets.py:260–280` — see existing `ClientAuditEventRow` pattern
3. Run `PEARL_LOCAL=1 pytest tests/ -q` to establish baseline
4. Add `maxLength`/`maxItems` to tool schemas (mechanical — do all 50)
5. Add MCP tool audit write helper
6. Add rate limit headers
7. Add `profile_version` to `AllowanceProfileRow` + migration
8. Bump dependencies
9. Run tests

## Cross-agent questions

If you need a decision:
- Write it to `../../decisions.md` under `## Open Questions`
- Format: `[security-hardening] <question>`

## When you're done

Before raising your PR, update `../../sprint-progress.md`:
- Change your row's Status from `in-progress` to `pr-raised`
- Add the PR URL to the PR column
- Add any open items or gotchas to Notes that the merge coordinator needs to know

Then raise your PR:
```bash
git fetch origin && git rebase origin/main
gh pr create --title "<task summary>" --base main
```

Do NOT merge directly to main — the main session coordinates merges in order.

## Pre-merge checklist

- [ ] All acceptance criteria above are met
- [ ] `PEARL_LOCAL=1 pytest tests/ -q` passes with no regressions
- [ ] Only Scope section files modified
- [ ] No debug code, no commented-out blocks
- [ ] Raise a PR — do NOT merge directly to main:
      `git fetch origin && git rebase origin/main`
      `gh pr create --title "feat: security hardening — MCP validation, rate limit headers, allowance versioning" --base main`
