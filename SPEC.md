# SPEC — PeaRL Security Review

> Last updated: 2026-04-05
> Status: Active
> Context: Open-source research platform — ease of setup is a first-class requirement

## Overview

PeaRL is the model-free platform for human oversight and governance of the Secure Agent Dark Factory. It serves platform engineers, security teams, and researchers who need deterministic, auditable control over AI agent promotion and autonomy elevation. PeaRL enforces governance gates, approval workflows, and promotion controls without making model calls — trust adjudication belongs to MASS 2.0, human reviewers make final decisions on consequential elevation. As an OSS project, the design prioritises `git clone` → `docker compose up` → working demo over enterprise hardening. Security findings are triaged accordingly: **setup-convenience items are by design; code-quality and runtime-stability issues are not**.

## Goals

- Enforce RBAC-gated governance decisions (reviewer role required for approvals and exceptions)
- Provide a tamper-evident audit trail for all governance actions — valuable for AI behaviour research
- Block autonomous agent attack chains at the API and MCP layers
- Ship a working demo with zero manual config (`docker compose up` is the entire setup)
- Fix genuine code defects and runtime stability issues regardless of deployment context

## Constraints

- Auth must support both JWT (human users) and API keys (service accounts / CI)
- Governance gates must route to humans — agents must never self-approve
- `PEARL_LOCAL=1` is a test harness only — never enabled in staging or prod
- No `.env` or server config access from within agent sessions
- **OSS default credentials are intentional** — documented, expected, and consistent with tools like Grafana and Gitea

## Out of Scope (this version)

- Attribute-based access control (ABAC) — per-project ACLs beyond role hierarchy
- Automated secret rotation (JWT secret, API keys)
- Hardware security module (HSM) key storage
- SOC 2 / ISO 27001 certification audit trail
- End-to-end encryption at rest for finding/report payloads
- Hardening default credentials / secrets for production deployment (OSS users deploying to prod own this)
- HTTPS enforcement in compose stack (handled by operator's reverse proxy)

---

## Architecture

```
Browser / AI Agent
      │
      ▼
 Nginx (TLS)
      │
      ├──▶ FastAPI (src/pearl/)
      │        │  JWT + API Key middleware
      │        │  RBAC (viewer/operator/service_account/reviewer/admin)
      │        │  Rate limiting (slowapi + Redis)
      │        │
      │        ├──▶ PostgreSQL (ORM via SQLAlchemy async)
      │        ├──▶ Redis (token blocklist, rate limit, pub/sub)
      │        └──▶ MinIO / S3 (artifact storage)
      │
      └──▶ MCP Server (src/pearl/mcp/)
               43 tools, JSON Schema validated
               Governance gates enforced via same RBAC
```

**Stack:** FastAPI · SQLAlchemy async · PostgreSQL · Redis · React + TypeScript · Vite · JWT HS256/RS256 · scrypt KDF

**Workers** (6 registered in `src/pearl/workers/registry.py`):
`compile_context` · `scan_source` · `mass_scan` · `normalize_findings` · `generate_remediation_spec` · `report`

---

## Features

### Feature: JWT Authentication

**Status:** Complete
**Priority:** Critical

JWT access tokens (15-min) and refresh tokens (30-day) issued on login. Tokens validated on every request for `iss`, `aud`, `alg` claims. RFC 7515 `crit` header rejection implemented. API key auth supported as alternative via `X-API-Key` header.

**Acceptance criteria:**
- [x] Passwords hashed with scrypt (n=2^14, r=8, p=1) + 16-byte random salt
- [x] Timing-safe comparison via `secrets.compare_digest`
- [x] Refresh token blocklist via Redis on logout
- [x] JWT secret configurable via `PEARL_JWT_SECRET` env var
- [x] RFC 7515 `crit` header rejected before `decode()` call
- [ ] JWT secret rotation without invalidating active sessions
- [ ] Enforce minimum 32-byte secret length in production startup check
- [ ] Refresh token rotation — invalidate old token when new one issued

**Key files:**
- `src/pearl/api/routes/auth.py` — token issuance, password verify, crit header check
- `src/pearl/api/middleware/auth.py` — per-request validation

---

### Feature: RBAC Enforcement

**Status:** Complete
**Priority:** Critical

Five canonical roles enforced via `Depends(require_role(...))` on all sensitive endpoints. Reviewer role required for all governance decisions (approve/reject). Admin required for user management.

**Acceptance criteria:**
- [x] Canonical role set: `viewer · operator · service_account · reviewer · admin`
- [x] `decideApproval` gated to `reviewer` or `admin`
- [x] `decideException` gated to `reviewer` or `admin`
- [x] `createUser` gated to `admin`
- [x] User creation validates roles against `CANONICAL_ROLES`
- [ ] Service accounts blocked from creating exceptions without reviewer endorsement
- [ ] Resource-scoped ACL (per-project permissions) for multi-tenant installations

**Key files:**
- `src/pearl/dependencies.py` — `require_role`, `get_current_user`, role constants
- `src/pearl/api/routes/auth.py:251` — admin gate on user creation

---

### Feature: Governance Gates

**Status:** Complete
**Priority:** Critical

Promotion gates evaluated before creating approval requests. Human reviewer required to decide. Approval records store `decided_by`, `decider_role`, `reason`, `decided_at`. Exception workflow separate from approval workflow.

**Acceptance criteria:**
- [x] Approval creation → pending state, requires reviewer decision
- [x] Exception creation → pending state (not auto-approved)
- [x] Status progression enforced: `pending → approved | rejected`
- [x] `trace_id` threaded through all governance requests
- [ ] Exception creation gated to reviewer or admin (currently any authenticated user can request; reviewers decide)
- [ ] `expires_at` enforced on pending approvals — no indefinite hangs
- [ ] Webhook / SSE event fired on rejection (currently only on approval)
- [ ] `conditions` field on approval decisions validated against defined schema

**Key files:**
- `src/pearl/api/routes/approvals.py` — approval workflow
- `src/pearl/api/routes/exceptions.py` — exception workflow

---

### Feature: Audit Trail

**Status:** In Progress
**Priority:** Critical

Audit events recorded for governance actions and user management. HMAC key configured for integrity signing. ApprovalDecisionRepository stores full decision metadata.

**Acceptance criteria:**
- [x] Approval decisions logged with actor, role, reason, timestamp
- [x] `audit_hmac_key` configurable via env var
- [x] Audit events created for: user creation, API key creation, project deletion, bulk project deletion
- [ ] HMAC signature verified on every audit read (currently write-only)
- [ ] Audit events created for: user deletion, API key deletion
- [ ] Audit events immutable — no update/delete endpoints
- [ ] Log database timestamp + request-local timestamp to detect clock skew

**Key files:**
- `src/pearl/api/routes/audit.py` — query endpoints
- `src/pearl/api/routes/auth.py` — user/API key audit events
- `src/pearl/api/routes/admin.py` — project deletion audit events

---

### Feature: Secrets Management

**Status:** In Progress
**Priority:** Critical

Settings loaded from environment via `pydantic-settings` with `PEARL_` prefix. `.env.example` provided. Production paths support RS256 key files.

**Acceptance criteria:**
- [x] All secrets via `PEARL_` env vars
- [x] `.env.example` in repo, `.env` gitignored
- [x] JWT private/public key file paths for RS256
- [ ] Remove hardcoded bootstrap credentials from source (`main.py:34-36`)
- [ ] Generate random admin password on first boot, log once, require change
- [ ] Bootstrap API key generated per-environment (not hardcoded in `docker-compose.yaml`)
- [ ] Default JWT secret rejected at startup if value is `"dev-secret-change-in-production"`
- [ ] `audit_hmac_key` default rejected in production mode
- [ ] S3 default credentials (`minioadmin`) rejected in production mode

**Key files:**
- `src/pearl/config.py` — all `PEARL_*` settings
- `src/pearl/main.py:30-48` — bootstrap admin seeding ⚠
- `docker-compose.yaml:13,80` — hardcoded secrets ⚠

---

### Feature: CORS Policy

**Status:** Complete
**Priority:** High

CORS configured via `PEARL_CORS_ALLOWED_ORIGINS` env var. Methods and headers are explicitly enumerated (no wildcards). Defaults to localhost origins for dev.

**Acceptance criteria:**
- [x] Origins configurable via env var (not hardcoded `["*"]`)
- [x] Dev default restricts to `localhost:5173`, `localhost:3000`
- [x] `allow_methods` explicitly enumerated — no `["*"]` wildcard
- [x] `allow_headers` explicitly whitelisted — no `["*"]` wildcard
- [ ] Production startup rejects wildcard `*` origin with `allow_credentials=True`
- [ ] Origins validated as HTTPS in non-local environments

**Key files:**
- `src/pearl/main.py` — CORS middleware config

---

### Feature: Rate Limiting

**Status:** In Progress
**Priority:** High

slowapi with Redis backend. Read: 1000/min, Write: 100/min. Per-user/IP key function. Missing slowapi logs a warning (previously silent).

**Acceptance criteria:**
- [x] Separate read/write limits configured
- [x] Per-user rate key (not IP-only)
- [x] Missing `slowapi` logs a startup warning (not silently ignored)
- [ ] Startup fails with clear error if `slowapi` not installed (currently degrades gracefully)
- [ ] In-memory fallback limiter when Redis unavailable
- [ ] Bulk/expensive endpoints (scan, bulk delete) have separate lower limits
- [ ] Rate limit headers returned in responses (`X-RateLimit-*`)

**Key files:**
- `src/pearl/api/middleware/rate_limit.py`
- `src/pearl/config.py` — limits config

---

### Feature: Input Validation

**Status:** In Progress
**Priority:** High

Pydantic models on all request bodies. SQLAlchemy ORM prevents parameterised injection. Dynamic table names in admin delete routes protected by an exhaustive whitelist + guard function.

**Acceptance criteria:**
- [x] Request bodies validated via Pydantic BaseModel
- [x] Enum constraints on severity, environment, status fields
- [x] ORM-based queries (no raw SQL in routes)
- [x] Dynamic table names in `admin.py` guarded by `_checked_table()` whitelist (raises on unknown tables)
- [x] Path traversal blocked in scan routes — `resolve(strict=True)` + forbidden prefix list
- [ ] `maxLength` added to all Pydantic string fields (title, description, rationale, etc.)
- [ ] SSRF protection on user-supplied URLs (scan targets, webhooks) — block RFC1918 ranges
- [ ] CVE ID format validation (`CVE-\d{4}-\d{4,}`)

**Key files:**
- `src/pearl/api/routes/admin.py` — `_PROJECT_TABLES` whitelist + `_checked_table()` guard
- `src/pearl/api/routes/scanning.py` — path traversal protection
- `src/pearl/api/routes/findings.py` — finding ingestion validation

---

### Feature: MCP Tool Safety

**Status:** In Progress
**Priority:** High

50 MCP tools with JSON Schema input validation. Governance gates enforced via same RBAC as REST API. No self-approval path exists. `pearl_allowance_check` tool added in dark factory sprint.

**Acceptance criteria:**
- [x] `decideApproval` requires reviewer role (enforced via API — not MCP-only)
- [x] Input schemas use pattern/enum constraints on IDs
- [x] Self-approval path blocked (create request ≠ decide request)
- [x] `pearl_allowance_check` tool — 3-layer allowance profile enforcement
- [ ] `maxLength` / `maxItems` added to all string/array tool arguments
- [ ] Audit event written on every MCP tool call (GAP-10)
- [ ] Per-tool rate limiting (separate quota from REST endpoints)
- [ ] Tool schema versioning — deprecation path for breaking changes

**Key files:**
- `src/pearl/mcp/tools.py` — tool schemas (50 tools)
- `src/pearl_dev/unified_mcp.py` — MCP server bindings

---

### Feature: Frontend Auth

**Status:** Complete
**Priority:** High

JWT login page, AuthContext with token persistence, RequireAuth route guard, user identity + role display in sidebar. 14 pages total.

**Acceptance criteria:**
- [x] Login page with email + password form
- [x] JWT stored in localStorage, used on all API requests
- [x] Route guard redirects to `/login` when unauthenticated
- [x] Sidebar shows current user roles + sign-out button
- [ ] Migrate token storage from `localStorage` to `sessionStorage` or HttpOnly cookies
- [ ] Add `Content-Security-Policy` header (via Nginx or FastAPI middleware)
- [ ] Add security headers: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`
- [ ] Auto-redirect to login on `401` response from API

**Key files:**
- `frontend/src/context/AuthContext.tsx` — token lifecycle
- `frontend/src/pages/LoginPage.tsx`
- `frontend/src/components/layout/RequireAuth.tsx`

---

### Feature: Attack Chain Defences

**Status:** Complete
**Priority:** High

7-level autonomous agent attack chain test suite. Covers MCP tool abuse, API auth bypass, privilege escalation.

**Acceptance criteria:**
- [x] L1: MCP tool abuse — service account cannot self-approve
- [x] L3: API auth bypass — auth middleware blocks unauthenticated requests
- [x] Tool description safety — no injection via tool descriptions
- [x] L2: Token escalation — refresh token replay after logout blocked
- [ ] L4: Governance bypass — test exception creation without reviewer approval
- [x] L5: Audit spoofing — audit records cannot be forged (HMAC mismatch detected)

**Key files:**
- `tests/security/attack_chain/` — L1, L3 tests
- `tests/security/test_tool_description_safety.py`

---

---

### Feature: Agent Allowance Profiles

**Status:** Complete
**Priority:** Critical

Three-layer deterministic pre-tool enforcement for Dark Factory agents. Baseline rules per agent type, environment tier overrides (permissive/standard/strict/locked), and per-task extensions from task packet. Sub-50ms check endpoint returns `{allowed, reason, layer, matched_rule}`.

**Acceptance criteria:**
- [x] `AllowanceProfileRow` model with `alp_` ID prefix
- [x] `AllowanceProfileRepository` with get/list/create/update/check
- [x] `POST /allowance-profiles/{id}/check` — 3-layer merge, sub-50ms
- [x] `GET /task-packets/{id}/allowance` — resolved merged profile
- [x] `allowed_paths` + `pre_approved_commands` JSON fields on `TaskPacketRow`
- [x] `pearl_allowance_check` MCP tool

**Key files:**
- `src/pearl/db/models/allowance_profile.py`
- `src/pearl/api/routes/allowance_profiles.py`
- `src/pearl/mcp/tools.py` — pearl_allowance_check tool

---

### Feature: Execution Phase Tracking

**Status:** Complete
**Priority:** High

Execution phase state machine on TaskPackets. Legal transitions: `planning → coding → testing → review → complete | failed`. Phase history recorded per transition with agent_id. Backward transitions rejected 422.

**Acceptance criteria:**
- [x] `execution_phase` (default "planning") + `phase_history` JSON on `TaskPacketRow`
- [x] `PATCH /task-packets/{id}/phase` with transition validation
- [x] Phase history entry: `{phase, timestamp, agent_id}`
- [x] `generateTaskPacket` MCP tool response includes `execution_phase`
- [x] Alembic migration `002_add_execution_phase_to_task_packets.py`

**Key files:**
- `src/pearl/db/models/task_packet.py`
- `src/pearl/api/routes/task_packets.py`

---

### Feature: Trust Accumulation Gates

**Status:** Complete
**Priority:** High

Promotion gates accumulate trust over time. Gates flip to `auto_pass=True` once `pass_count >= auto_pass_threshold` (default 5). Auto-pass blocked if open `drift_trend` findings exist. Human-approved promotions increment `pass_count`.

**Acceptance criteria:**
- [x] `auto_pass`, `pass_count`, `auto_pass_threshold` on `PromotionGateRow`
- [x] Gate evaluator: auto-decide approval if auto_pass=True and no open drift_trend findings
- [x] `pass_count` increments only on human-approved promotions
- [x] `PATCH /gates/{id}` for admin to set `auto_pass_threshold`
- [x] Alembic migration `003_add_trust_accumulation_to_gates.py`

**Key files:**
- `src/pearl/db/models/promotion.py`
- `src/pearl/services/promotion/gate_evaluator.py`

---

### Feature: Behavioral Drift Signal

**Status:** Complete
**Priority:** High

Two behavioral drift finding subtypes: `drift_acute` (hard stop, logged) and `drift_trend` (pattern drift, blocks gate auto-pass flip). Resolving a `drift_trend` finding re-enables auto-pass evaluation. Dashboard includes behavioral drift count.

**Acceptance criteria:**
- [x] `behavioral_drift` source and `drift_acute` / `drift_trend` categories in enums
- [x] Open `drift_trend` findings block gate auto-pass flip
- [x] Resolving `drift_trend` re-enables auto-pass evaluation
- [x] Behavioral drift count in dashboard summary

**Key files:**
- `src/pearl/models/enums.py`
- `src/pearl/services/promotion/gate_evaluator.py`

---

### Feature: Workload Registry

**Status:** Complete
**Priority:** High

SPIRE SVID → task packet mapping for control-room visibility. Agents register on startup, send heartbeats, deregister on exit. Workloads with no heartbeat > 5 min auto-transition to inactive (on-read). SSE events for real-time dashboard.

**Acceptance criteria:**
- [x] `WorkloadRow` with `wkld_` ID prefix, SVID unique index
- [x] `POST /workloads/register` + `POST /workloads/{svid}/heartbeat` + `DELETE /workloads/{svid}` + `GET /workloads`
- [x] On-read inactive timeout (last_seen_at > 5 min → inactive)
- [x] SSE events: `workload.registered`, `workload.deregistered`
- [x] `active_workload_count` in `GET /dashboard`

**Key files:**
- `src/pearl/db/models/workload.py`
- `src/pearl/api/routes/workloads.py`

---

### Feature: Agent Registry

**Status:** Planned
**Priority:** Medium

Central registry of all agent configs, versions, owners, and quality scores (Dark Factory P5). Enables factory-level visibility into which agents are running what tasks, their version history, and deepagents-harbor quality scores. Long-term dependency for nemotron fine-tuning feedback loop.

**Acceptance criteria:**
- [ ] `AgentRow` model with `agnt_` ID prefix: `name`, `version`, `owner`, `config_path`, `quality_score`, `registered_at`, `last_active_at`
- [ ] `POST /agents/register` — register agent config + briefing hash
- [ ] `GET /agents` — list with quality scores, filterable by owner/version
- [ ] `GET /agents/{id}` — full agent record including version history
- [ ] Quality score update endpoint callable by deepagents-harbor eval runs
- [ ] `active_agent_count` added to `GET /dashboard` summary
- [ ] `pearl_agent_register` MCP tool for agents to self-register on startup

**Key files:**
- `src/pearl/db/models/agent_registry.py` — AgentRow (to create)
- `src/pearl/api/routes/agent_registry.py` — CRUD routes (to create)
- `src/pearl/mcp/tools.py` — pearl_agent_register tool (to add)

---


### Feature: Server-Authoritative Audit Trail (Security Sprint)

**Status:** Complete
**Priority:** Critical

Gap identified: governance actions (approval decisions, exception creates, gate evaluations, promotion requests) do not write server-authoritative audit records. The current `ClientAuditEventRow` depends on client-submitted data. Server must write its own immutable record at the point of action.

**Acceptance criteria:**
- [x] `AuditEventRow` written in `POST /approvals/{id}/decide` (approval granted/rejected)
- [x] `AuditEventRow` written in `POST /exceptions` (exception creation)
- [x] `AuditEventRow` written in gate evaluation (gate pass/fail)
- [x] `AuditEventRow` written in `POST /projects/{id}/promotions` (promotion request)
- [x] Audit records have no update/delete endpoints — immutable once written
- [x] HMAC signature computed and stored on write; verified on read
- [x] `GET /audit/events` requires `viewer` role minimum

**Key files:**
- `src/pearl/api/routes/approvals.py` — add audit write on decide
- `src/pearl/api/routes/exceptions.py` — add audit write on create
- `src/pearl/services/promotion/gate_evaluator.py` — add audit write on gate evaluate
- `src/pearl/api/routes/promotions.py` — add audit write on request
- `src/pearl/api/routes/audit.py` — add HMAC verification on read

---

### Feature: Security Hardening (Security Sprint)

**Status:** In Progress
**Priority:** High

Targeted hardening across rate limiting, MCP input validation, and dependency updates. No new endpoints — fixes to existing code quality gaps.

**Acceptance criteria:**
- [x] `maxLength` / `maxItems` added to all MCP tool string/array arguments
- [x] Audit event written on every MCP tool call (GAP-10)
- [ ] Agent cost reports immutable once submitted (write-once, no PATCH)
- [x] Allowance profile versioning — profile changes versioned, running agents not retroactively affected
- [x] `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers in all rate-limited responses
- [ ] Dependabot alerts resolved: aiohttp ×9 (medium/low), lodash ×2 (high/medium), picomatch ×2 (medium), Pygments (low), cryptography (low)

**Key files:**
- `src/pearl/mcp/tools.py` — maxLength/maxItems on all tool schemas
- `src/pearl/api/middleware/rate_limit.py` — add rate limit response headers
- `src/pearl/db/models/allowance_profile.py` — add version field

---

### Feature: Security Validation Suite (Security Sprint)

**Status:** In Progress
**Priority:** High

Contract tests and integration validation for the security sprint. Validates that audit trail, HMAC verification, and input validation work end-to-end. Attack chain L2, L4, L5 coverage.

**Acceptance criteria:**
- [x] Contract tests: `POST /approvals/{id}/decide` produces audit record
- [x] Contract tests: `POST /exceptions` produces audit record
- [x] Contract test: HMAC signature present and verifiable on audit read
- [x] L2 attack chain test: refresh token replay after logout blocked
- [ ] L4 attack chain test: exception creation without reviewer approval blocked
- [x] L5 attack chain test: audit record cannot be forged by client (xfail — SQLite HMAC timezone bug fixed in main session)
- [x] SPEC.md acceptance criteria validation script — `pytest tests/security/spec_validation.py`

**Key files:**
- `tests/contract/test_audit_trail.py` — CREATE
- `tests/security/attack_chain/` — add L2, L4, L5
- `tests/security/spec_validation.py` — CREATE

---

### Feature: Security Code Scanning Fixes (Cleanup Sprint)

**Status:** In Progress (6/9 criteria met — 3 antipatterns gaps carry to next sprint)
**Priority:** High

Four-track cleanup sprint addressing GitHub Code Scanning alerts (×17), httpx connection pool antipattern (×27, 10 files), CI/CD permissions hardening (×5), and Dependabot dependency alerts. Sprint merged. Three antipatterns criteria (WebhookRegistry cap, gate re-eval hard block, migration 005) were not implemented by the antipatterns agent — they carry forward as the highest-priority open tech debt.

**Acceptance criteria:**
- [x] Path injection fixed: `scanning.py:61`, `scanning.py:1240`, `service.py` ×7 — `resolve(strict=False)` + forbidden prefix + allowlist at route and service layer
- [x] httpx per-request clients replaced with shared class-level `AsyncClient` across 10 adapter files (27 occurrences)
- [x] API key hashing migrated from raw SHA256 → HMAC-SHA256 with `PEARL_API_KEY_HMAC_SECRET`
- [x] Stack trace exposure fixed in `integrations.py:215` and `:341` — generic message to user, full exc server-side logged only
- [x] GitHub Actions jobs have explicit least-privilege `permissions:` blocks (`ci.yml` ×4, `pearl-gate.yml` ×1)
- [x] Dependabot resolved: aiohttp, Pygments, cryptography (Python); picomatch ×2 (frontend); lodash pinned with stagnancy note
- [ ] WebhookRegistry capped at `PEARL_MAX_WEBHOOK_SUBSCRIPTIONS` (default 1000) — `ConflictError` on overflow *(antipatterns PR merged without this)*
- [ ] Gate re-evaluation in manual mode (`gate.auto_pass=False`) raises instead of swallowing exception — hard block enforced *(antipatterns PR merged without this — task_packets.py:293,344,432 still bare except)*
- [ ] Raw `ALTER TABLE` calls removed from `main.py` lifespan, replaced with Alembic migration `005_cleanup_lifespan_alters.py` *(antipatterns PR merged without this)*

**Key files:**
- `src/pearl/api/routes/scanning.py` — path injection fixes (scanning-fixes)
- `src/pearl/scanning/service.py` — service-layer path guard (scanning-fixes)
- `src/pearl/integrations/adapters/` — httpx pool refactor, 10 files (scanning-fixes)
- `src/pearl/api/middleware/auth.py` — API key HMAC fix (auth-hardening)
- `src/pearl/api/routes/integrations.py` — stack trace sanitization (auth-hardening)
- `.github/workflows/ci.yml`, `.github/workflows/pearl-gate.yml` — permissions (ci-deps)
- `pyproject.toml` + `frontend/package.json` — dependency bumps (ci-deps)
- `src/pearl/events/webhook_config.py` — subscription cap (antipatterns)
- `src/pearl/api/routes/task_packets.py:336` — gate re-eval hard block (antipatterns)
- `src/pearl/main.py` — remove ALTER TABLE, add Alembic migration (antipatterns)

---


### Feature: MASS 2.0 / Snyk SCA Integration

**Status:** Complete
**Priority:** High

Ingest routes for Snyk SCA (`snyk test --json`) and MASS 2.0 AI scan output. Findings upserted into PeaRL and wired to gate rules. Auto-resolves stale findings not present in the latest scan.

**Acceptance criteria:**
- [x] `POST /projects/{id}/integrations/snyk/ingest` — ingests Snyk vulnerability JSON, upserts findings
- [x] `POST /projects/{id}/integrations/mass/ingest` — ingests MASS 2.0 scan results
- [x] `SNYK_OPEN_HIGH_CRITICAL` gate rule evaluates open critical/high Snyk vulns
- [x] `AI_SCAN_COMPLETED` and `AI_RISK_ACCEPTABLE` gate rules use real MASS data
- [x] Stale findings from prior scans auto-resolved on new ingest

**Key files:**
- `src/pearl/api/routes/scanning.py` — ingest routes
- `src/pearl/services/promotion/gate_evaluator.py` — SNYK/MASS gate rule logic
- `src/pearl/models/enums.py` — `SNYK_OPEN_HIGH_CRITICAL`, `AI_SCAN_COMPLETED`, `AI_RISK_ACCEPTABLE`

---

## Known Tech Debt

### By Design — OSS/Research Setup Convenience (not action items)

| Area | Notes |
|---|---|
| `src/pearl/main.py:34-36` — hardcoded bootstrap credentials | Intentional first-boot seed. Standard OSS practice (cf. Grafana, Portainer). Documented in README. |
| `docker-compose.yaml:13` — default JWT secret | Dev compose config. Users deploying to prod are expected to override via env var. |
| `docker-compose.yaml:80` — API key in frontend env | Dev convenience fallback; login flow takes precedence when JWT is present. |
| `src/pearl/api/routes/exceptions.py:52` — exception creation requires only auth | Design choice: operators can *request* exceptions; reviewers *decide*. Gate is on the decide endpoint. |
| `src/pearl/config.py:74` — default audit HMAC key | Dev default consistent with JWT secret pattern. Prod operators override. |
| MinIO `minioadmin` defaults | MinIO's own default; compose users expect it. |
| `frontend/src/context/AuthContext.tsx:61` — JWT in localStorage | Acceptable for research use. Noted for any user-facing deployment. |

### Real Issues — Resolved

| Area | Issue | Fix |
|---|---|---|
| `src/pearl/api/routes/admin.py` | Dynamic table names via f-strings — injection risk | ✅ Fixed: `_PROJECT_TABLES` frozenset whitelist + `_checked_table()` guard |
| `src/pearl/main.py` | CORS `allow_methods=["*"]` and `allow_headers=["*"]` | ✅ Fixed: explicit method/header lists, origins via env var |
| `src/pearl/api/middleware/rate_limit.py` | Missing `slowapi` silently disabled rate limiting | ✅ Fixed: `logger.warning()` on import failure |
| `src/pearl/api/routes/auth.py` | No audit events on user/API key creation | ✅ Fixed: audit events appended after each create |
| `src/pearl/api/routes/admin.py` | No audit events on project deletion | ✅ Fixed: `project.deleted` and `project.bulk_deleted` events |
| `src/pearl/scanning/integrations/security_review.py` | Polynomial ReDoS in 3 regex patterns | ✅ Fixed: bounded `[^...\n]{1,N}` char classes + 500KB input cap |
| `src/pearl/api/routes/scanning.py` | Path traversal via unresolved scan target path | ✅ Fixed: `resolve(strict=True)` + forbidden prefix check |

### Real Issues — Open

| Area | Issue | Severity | Sprint |
|---|---|---|---|
| `src/pearl/api/routes/audit.py` | No HMAC verification on audit reads — research value of audit trail undermined | Medium | server-audit-trail |
| `src/pearl/api/routes/approvals.py` | No server-authoritative audit record on approval decisions | High | server-audit-trail |
| `src/pearl/api/routes/exceptions.py` | No server-authoritative audit record on exception creation | High | server-audit-trail |
| `src/pearl/api/routes/promotions.py` | No server-authoritative audit record on promotion requests | High | server-audit-trail |
| `src/pearl/mcp/tools.py` | No `maxLength`/`maxItems` on tool arguments — unbounded inputs | Medium | security-hardening |
| `src/pearl/mcp/tools.py` | No audit event per MCP tool call (GAP-10) | Medium | security-hardening |
| `src/pearl/db/models/allowance_profile.py` | No version field — profile changes affect running agents retroactively | Medium | security-hardening |
| `src/pearl/api/middleware/rate_limit.py` | No `X-RateLimit-*` response headers | Low | security-hardening |
| `src/pearl/api/routes/auth.py:143` | Refresh tokens not rotated on refresh — old token remains valid until expiry | Low | — |
| `src/pearl/api/routes/scanning.py:61,:1240` | Path injection — user-supplied path not validated before filesystem access (×8 GitHub Code Scanning) | High | scanning-fixes |
| `src/pearl/integrations/adapters/` ×10 files | httpx per-request `AsyncClient()` — connection pool exhaustion under load (27 occurrences) | High | scanning-fixes |
| `src/pearl/api/middleware/auth.py:97` | API key hashed with raw SHA256 — CodeQL py/weak-sensitive-data-hashing | Medium | auth-hardening |
| `src/pearl/api/routes/integrations.py:215,:341` | Stack trace exposed in API error response — CodeQL py/stack-trace-exposure | Medium | auth-hardening |
| `.github/workflows/ci.yml`, `pearl-gate.yml` | Jobs missing explicit `permissions:` blocks — overly broad default token (×5) | Medium | ci-deps |
| `src/pearl/events/webhook_config.py` | `_subscriptions` unbounded in-memory list — no cap, no persistence, restarts lose all registrations | High | antipatterns |
| `src/pearl/api/routes/task_packets.py:336` | `bare except: pass` after gate re-evaluation — manual mode silently returns 200 on failure | High | antipatterns |
| `src/pearl/main.py` | Raw `ALTER TABLE` calls in app lifespan bypass Alembic — diverge between SQLite and PostgreSQL | High | antipatterns |

## Open Questions

- [ ] Multi-tenant project ACL: is per-org data isolation required, or is single-org sufficient for research use?
- [ ] HttpOnly cookie migration for token storage — is this needed before any public-facing deployment?
- [ ] Should exception *creation* (not just decision) require reviewer role to prevent operator flooding the queue?
