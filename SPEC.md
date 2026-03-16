# SPEC — PeaRL Security Review

> Last updated: 2026-03-16
> Status: Active
> Context: Open-source research platform — ease of setup is a first-class requirement

## Overview

PeaRL (Policy-enforced Autonomous Risk Layer) is an open-source research platform that enforces governance gates between AI agents and production deployments. It serves researchers, platform engineers, and security teams studying human-in-the-loop AI control. As a research/OSS project, the design prioritises `git clone` → `docker compose up` → working demo over enterprise hardening. Security findings are triaged accordingly: **setup-convenience items are by design; code-quality and runtime-stability issues are not**.

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

**Status:** Complete
**Priority:** High

43 MCP tools with JSON Schema input validation. Governance gates enforced via same RBAC as REST API. No self-approval path exists.

**Acceptance criteria:**
- [x] `decideApproval` requires reviewer role (enforced via API — not MCP-only)
- [x] Input schemas use pattern/enum constraints on IDs
- [x] Self-approval path blocked (create request ≠ decide request)
- [ ] `maxLength` / `maxItems` added to all string/array tool arguments
- [ ] Per-tool rate limiting (separate quota from REST endpoints)
- [ ] Tool schema versioning — deprecation path for breaking changes

**Key files:**
- `src/pearl/mcp/tools.py` — tool schemas (43 tools)
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
- [ ] L2: Token escalation — test refresh token replay after logout
- [ ] L4: Governance bypass — test exception creation without reviewer approval
- [ ] L5: Audit spoofing — test that audit records cannot be forged

**Key files:**
- `tests/security/attack_chain/` — L1, L3 tests
- `tests/security/test_tool_description_safety.py`

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

| Area | Issue | Severity |
|---|---|---|
| `src/pearl/api/routes/audit.py` | No HMAC verification on audit reads — research value of audit trail undermined | Medium |
| `src/pearl/api/routes/auth.py:143` | Refresh tokens not rotated on refresh — old token remains valid until expiry | Low |

## Open Questions

- [ ] Multi-tenant project ACL: is per-org data isolation required, or is single-org sufficient for research use?
- [ ] HttpOnly cookie migration for token storage — is this needed before any public-facing deployment?
- [ ] Should exception *creation* (not just decision) require reviewer role to prevent operator flooding the queue?
