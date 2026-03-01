# PeaRL Architecture

## System Overview

PeaRL is a policy-enforced governance layer between AI coding agents and production environments. It enforces security gates, approval workflows, fairness requirements, and compliance checks before any AI-driven change reaches users.

Core responsibilities:
1. **Onboard and configure** projects, org baselines, and application specs via MCP or API
2. **Ingest and normalize** findings from scanners (Snyk, Semgrep, Trivy) and security reviews
3. **Compile context** packages for agent consumption — with signed receipts to track what each agent was shown
4. **Generate and track** remediation task packets claimed and completed by agents
5. **Gate promotions** through configurable rule evaluators (findings, approvals, fairness, evidence, compliance)
6. **Orchestrate human review** for approvals and exceptions with role-enforced decide endpoints
7. **Emit and stream** governance telemetry, audit events, and cost ledger data in real time
8. **Enforce security** against autonomous agent bypass attempts at the API, MCP, and file layers

---

## Component Diagram

```
External Systems            PeaRL Core                        Data Stores
────────────────            ──────────────────────────────    ────────────

                            ┌──────────────────────────────┐
AI Agents (MCP)  ──────────▶│   FastAPI REST API            │──▶  PostgreSQL
                            │   /api/v1 (33 route files)    │       (primary)
Claude / Codex   ──────────▶│   Auth: JWT Bearer / API Key  │
                            │   RBAC: operator/reviewer/    │──▶  Redis
CI/CD systems    ──────────▶│         admin/service_account │       (job queue)
                            │   Middleware: Auth, RateLimit, │       (SSE pub/sub)
Dashboard (React)──────────▶│             TraceID           │       (scheduler lock)
                            └──────────────┬───────────────┘
                                           │
                            ┌──────────────▼───────────────┐
Scanners                    │   Background Workers          │──▶  MinIO / S3
  Snyk / Semgrep ──────────▶│   compile_context             │       (reports)
  Trivy          ──────────▶│   scan_source                 │
                            │   normalize_findings           │
                            │   generate_remediation_spec    │
                            │   report                       │
                            └──────────────┬───────────────┘
                                           │
                            ┌──────────────▼───────────────┐
                            │   Scheduler                   │
                            │   (60s poll, Redis lock)      │
                            │   Enqueues periodic scans     │
                            └──────────────────────────────┘
```

---

## API Surface

**Base path:** `/api/v1` — 33 route files, ~130 endpoints

### Route Groups

| Area | Files | Key Endpoints |
|---|---|---|
| **Auth & Users** | `auth.py` | `POST /auth/login`, `/auth/refresh`, `/auth/logout`, `GET /auth/jwks.json`, `POST /users`, `GET /users/me`, `POST /users/me/api-keys` |
| **Projects** | `projects.py`, `project_inputs.py` | CRUD `/projects`, `GET /projects/{id}/pearl.yaml`, `GET /projects/{id}/mcp.json` |
| **Onboarding** | `onboarding.py` | `GET /onboarding/setup` — returns pre-built Claude Code batch file + setup guide |
| **Context** | `context.py`, `compile.py` | `POST /projects/{id}/compile`, `GET /projects/{id}/compiled-package`, `POST /compiled-packages/{id}/receipt` |
| **Findings** | `findings.py`, `audit.py` | Ingest, list, triage, bulk-status (reviewer-gated for `false_positive`) |
| **Governance** | `approvals.py`, `exceptions.py` | `POST /approvals/{id}/decide` (reviewer only), `POST /exceptions/{id}/decide` (reviewer only), exception review workflow |
| **Promotions** | `promotions.py` | `POST /projects/{id}/promotions/evaluate`, `/request`, `/rollback` (admin) |
| **Remediation** | `remediation.py`, `task_packets.py`, `agent.py` | Generate, claim, complete task packets; agent interaction endpoints |
| **Scanning** | `scanning.py`, `scan_targets.py` | Register/manage scan targets, trigger scans, retrieve results |
| **Compliance** | `compliance.py`, `fairness.py`, `guardrails.py`, `requirements.py` | Fairness cases, evidence packages, guardrail evaluation, framework requirements |
| **Telemetry** | `governance_telemetry.py` | `POST /projects/{id}/audit-events` (batch, max 500), `POST /projects/{id}/cost-entries` (batch, max 500) |
| **Config** | `org_env_config.py` | Org-level environment configuration, policy overrides |
| **Reporting** | `reports.py` | Generate and retrieve compliance/risk reports |
| **Analytics** | `dashboard.py`, `timeline.py`, `business_units.py`, `pipelines.py` | Dashboard summaries, audit timelines, business unit management, pipeline status |
| **Infrastructure** | `health.py`, `stream.py`, `jobs.py`, `integrations.py`, `slack_interactions.py` | Health/readiness probes, SSE events, job status, third-party integrations |

### Health Endpoints

| Endpoint | Purpose |
|---|---|
| `GET /health/live` | K8s liveness — always 200 |
| `GET /health/ready` | K8s readiness — checks DB (SELECT 1) + Redis (PING); 503 if either fails |
| `GET /server-config` | Returns `reviewer_mode`, `local_mode` flags; used by dashboard to show governance banners |
| `GET /metrics` | Prometheus metrics via prometheus-fastapi-instrumentator |

---

## MCP Integration

PeaRL exposes **39 tools** via MCP for AI agent integration. The server is in `src/pearl_dev/unified_mcp.py`; tool definitions are in `src/pearl/mcp/tools.py`.

### Tool Catalogue

| Category | Tools |
|---|---|
| **Project Management** | `createProject`, `getProject`, `updateProject`, `getProjectSummary` |
| **Project Configuration** | `upsertOrgBaseline`, `upsertApplicationSpec`, `upsertEnvironmentProfile` |
| **Context** | `compileContext`, `getCompiledPackage`, `submitContextReceipt` |
| **Findings & Remediation** | `ingestFindings`, `generateRemediationSpec`, `generateTaskPacket`, `claimTaskPacket`, `completeTaskPacket` |
| **Governance** | `createApprovalRequest`, `decideApproval`, `createException`, `requestPromotion`, `evaluatePromotionReadiness`, `getPromotionReadiness`, `getPromotionHistory` |
| **Compliance & Fairness** | `createFairnessCase`, `submitEvidence`, `assessCompliance`, `listGuardrails`, `getGuardrail`, `getRecommendedGuardrails`, `getRecommendedBaseline`, `applyRecommendedBaseline`, `listPolicyTemplates`, `getPolicyTemplate`, `ingestSecurityReview` |
| **Scanning** | `registerScanTarget`, `listScanTargets`, `updateScanTarget`, `runScan`, `getScanResults` |
| **Monitoring & Jobs** | `ingestMonitoringSignal`, `getJobStatus` |
| **Reports** | `generateReport` |

### Governance-Sensitive Tools

`decideApproval` and `createException` are gated: the underlying API endpoints require the `reviewer` role. If called without reviewer access, the tools return `_human_action_required: true` with a dashboard URL — the agent sees it cannot self-approve and must surface the action to a human.

---

## Onboarding Flow

`GET /onboarding/setup` returns a pre-configured Windows batch file (`Claude Code.bat`) that:

1. Opens a folder browser (PowerShell COM dialog)
2. Converts the selected Windows path to WSL path format
3. Writes `.mcp.json` to the project folder if absent (auto-configures PeaRL MCP tools)
4. Runs `pearl_hook_check.py` to auto-register the project in PeaRL if `.pearl.yaml` exists
5. Hints the developer to call `createProject` via MCP for new projects
6. Launches `claude` in the project directory via WSL

Once a project is registered, its config files are downloadable at:
- `GET /api/v1/projects/{id}/pearl.yaml` — project governance config
- `GET /api/v1/projects/{id}/mcp.json` — pre-filled `.mcp.json` for that project

---

## Data Flow

### Promotion Gate Flow

```
POST /projects/{id}/promotions/evaluate
  → GateEvaluator checks rules:
      - Active findings (severity × environment thresholds)
      - Pending / rejected approvals
      - Fairness requirements (if ai_enabled)
      - Evidence attestations (if required by environment)
      - Compliance framework checks
  → PromotionEvaluationRow (pass/fail per rule)
  → If all pass: POST /promotions/request → PromotionHistoryRow
  → If blocked:  human approval required via /approvals
                 or exception via /exceptions (reviewer role to decide)
```

### Agent Task Packet Flow

```
POST /projects/{id}/task-packets (generate)
  → CompileContextWorker builds context
  → GenerateRemediationWorker produces spec
  → TaskPacketRow created with signed artifact hashes

POST /task-packets/{id}/claim  (agent claims)
  → agent_id, claimed_at set

Agent executes changes

POST /task-packets/{id}/complete (agent reports)
  → outcome recorded
  → resolved FindingRows updated to status="resolved"
  → ClientAuditEventRow created (governance telemetry)
```

### Context Receipt Flow

```
POST /projects/{id}/compile
  → CompiledPackageRow created (artifact hashes, policy snapshot)

Agent calls submitContextReceipt MCP tool
  → ContextReceiptRow records: commit_hash, agent_id,
    tool_calls_made, artifact_hashes_seen, consumed_at
  → Provides audit trail of what the agent was shown
```

### Finding Ingestion Flow

```
POST /projects/{id}/findings/ingest (or ingestFindings MCP tool)
  → FindingBatchRow + FindingRows created (status="open")
  → normalize_findings job enqueued
  → NormalizeFindingsWorker: sets normalized=True, score, severity
  → SSE event published: "finding_batch_ingested"
```

---

## Database Schema

### Core Entities

```
OrgRow
  └─▶ BusinessUnitRow (org_id)
  └─▶ UserRow (org_id)
  │    └─▶ ApiKeyRow (user_id) — SHA-256 hash, expiry, last_used_at
  └─▶ ProjectRow (org_id)
       └─▶ OrgBaselineRow      — org-wide security defaults
       └─▶ AppSpecRow          — components, trust boundaries, data, RAI settings
       └─▶ EnvironmentProfileRow
       └─▶ OrgEnvConfigRow     — per-env policy overrides
       └─▶ FindingRow
       │    └─▶ FindingBatchRow
       └─▶ ApprovalRequestRow
       │    └─▶ ApprovalDecisionRow
       │    └─▶ ApprovalCommentRow
       └─▶ ExceptionRecordRow
       └─▶ TaskPacketRow
       └─▶ RemediationSpecRow
       └─▶ CompiledPackageRow  — pre-compiled context snapshot + artifact hashes
       └─▶ ReportRow
       └─▶ JobRow
       └─▶ ScanTargetRow
       └─▶ PromotionHistoryRow
       └─▶ PolicyVersionRow    — policy change audit trail
```

### Fairness & Compliance

```
ProjectRow
  └─▶ FairnessCaseRow            — risk_tier, fairness_criticality, case_data
  └─▶ FairnessRequirementsSpecRow — requirements JSON, version
  └─▶ FairnessExceptionRow        — requirement_id, compensating_controls,
  │                                  approved_by, expires_at
  └─▶ EvidencePackageRow          — evidence_type, attestation_status,
  │                                  evidence_data, expires_at
  └─▶ FrameworkRequirementRow     — compliance framework items
```

### Telemetry & Observability

```
ProjectRow
  └─▶ ClientAuditEventRow   — pushed from agents: action, decision, tool_name, reason
  └─▶ ClientCostEntryRow    — pushed from agents: model, cost_usd, duration_ms,
                               num_turns, tools_called, session_id
```

### Infrastructure

```
IntegrationRow     — third-party integration config per org
NotificationRow    — notification/alert delivery records
IdempotencyRow     — request deduplication by idempotency key
```

---

## Auth Architecture

```
Request
  │
  ▼
AuthMiddleware
  ├─ Bearer <token>   → JWT decode (python-jose)
  │    ├─ HS256 (PEARL_LOCAL=1 / local dev)
  │    └─ RS256 / OIDC (production, PEARL_JWT_ALGORITHM=RS256)
  │
  ├─ X-API-Key: <key> → SHA-256 hash lookup → ApiKeyRow → UserRow
  │    └─ Checks: is_active, expires_at, last_used_at updated
  │
  └─ No auth → anonymous (health, login, jwks, server-config pass through)
       │
       ▼
  request.state.user = {sub, roles, scopes, email}
       │
       ▼
  Route handler dependencies:
    Depends(get_current_user)    — any authenticated user
    Depends(require_role("admin"))  — admin-only
    Depends(RequireReviewer)        — reviewer role for governance decide endpoints
```

### Local Dev Auth Modes

| Flag | Roles Granted | Use Case |
|---|---|---|
| `PEARL_LOCAL=1` | `operator` | Development — agents can create/request but not decide |
| `PEARL_LOCAL=1` + `PEARL_LOCAL_REVIEWER=1` | `operator` + `security_reviewer` | Dashboard reviewer session (set manually by human reviewer only) |
| Neither | Full JWT/API key auth | Production |

### Reviewer Role Gate

Endpoints that modify governance decisions require the reviewer role:

| Endpoint | Gate |
|---|---|
| `POST /approvals/{id}/decide` | `RequireReviewer` |
| `POST /exceptions/{id}/decide` | `RequireReviewer` |
| `PATCH /projects/{id}/findings/{id}/status` (false_positive) | `RequireReviewer` |
| `POST /projects/{id}/findings/bulk-status` (false_positive) | `RequireReviewer` |

`REVIEWER_ROLES = ("security_reviewer", "security_analyst", "security_manager", "governance", "admin")`

---

## Worker Architecture

```
Redis List: pearl:jobs:{job_type}
  │
  ▼
Worker Process (asyncio)
  │
  ├─ Pop job from list
  ├─ Update JobRow status → "running"
  ├─ Call BaseWorker.process()
  │    ├─ On success: status → "succeeded", result_refs set
  │    └─ On error: retry up to max_retries=3, then "failed"
  └─ Commit to DB

Worker Registry (src/pearl/workers/registry.py):
  "compile_context"           → CompileContextWorker
  "scan_source"               → ScanWorker
  "normalize_findings"        → NormalizeFindingsWorker
  "generate_remediation_spec" → GenerateRemediationWorker
  "report"                    → GenerateReportWorker
```

---

## Real-Time Events (SSE)

`GET /stream/events` — Redis pub/sub backend, consumed by the dashboard.

```
API action publishes event
  → redis.publish("pearl:events:broadcast", json)      ← all connected clients
  → redis.publish("pearl:events:user:{user_id}", json) ← targeted user

Browser EventSource (dashboard)
  ← SSE stream delivers events in real time
```

Events emitted on: approval created/decided, exception created/decided, gate failure, finding batch ingested, task packet claimed/completed, promotion requested.

---

## Autonomous Agent Security Model

PeaRL was red-team tested with an autonomous AI agent (Claude Sonnet 4.6) that demonstrated a 7-level privilege escalation chain targeting self-approval of governance exceptions. The following hard controls are deployed as a result.

See full research: [`docs/security_research/pearl_autonomous_attack_research.md`](./security_research/pearl_autonomous_attack_research.md)
See operational hardening guide: [`docs/security_research/SECURITY_HARDENING.md`](./security_research/SECURITY_HARDENING.md)

### Hard Controls

| Control | Blocks | Where |
|---|---|---|
| `PEARL_LOCAL=1` grants `operator` only — not reviewer | L3 direct API exploit | `src/pearl/config.py` |
| `RequireReviewer` on all decide endpoints | L3, L4 | `src/pearl/dependencies.py` |
| `false_positive` status requires reviewer role | L4 evidence poisoning | `src/pearl/api/routes/findings.py` |
| OpenAPI schema hidden in production (`PEARL_EXPOSE_OPENAPI`) | L2 schema discovery | `src/pearl/api/middleware/auth.py` |
| `disallowedBashCommands` in `.mcp.json` | L3, L7 | `.mcp.json` |
| `PreToolUse` Bash guard hook (`scripts/pearl_bash_guard.py`) | L6, L7 | Hook script (install in `~/.claude/settings.json`) |
| 403 structured audit log (`governance_access_denied`) | Detection | `src/pearl/errors/handlers.py` |

### Soft Controls

| Control | Blocks | Where |
|---|---|---|
| CLAUDE.md governance constraints | L5, L6, L7 | `CLAUDE.md` |
| Stripped flag documentation from `.env.example` / `config.py` | L5 social engineering | Source files |
| Dashboard reviewer-mode warning banner | L5 | `GET /server-config` + frontend |

### Bash Guard Scope

The `pearl_bash_guard.py` hook blocks **only PeaRL-specific governance bypass patterns**:
- Direct curl calls to `/approvals/*/decide` or `/exceptions/*/decide`
- Shell commands writing `PEARL_LOCAL_REVIEWER` to any file

It does **not** block general development commands (`ps`, `kill`, `docker`, `systemctl`) which are needed for legitimate autonomous prototyping workflows.

---

## Observability

| Signal | Implementation |
|---|---|
| **Structured logs** | `structlog` — JSON in production, console in local |
| **Governance access denied** | `WARNING governance_access_denied` on every 403 AuthorizationError (path, user_sub, roles, trace_id) |
| **Request tracing** | `X-Trace-ID` header via TraceID middleware → `request.state.trace_id` |
| **Metrics** | Prometheus via `prometheus-fastapi-instrumentator` at `/metrics` |
| **Client telemetry** | Agents push audit events and cost entries via `POST /projects/{id}/audit-events` and `/cost-entries` |

---

## Key Files Reference

| File | Purpose |
|---|---|
| `src/pearl/main.py` | App factory, lifespan, middleware registration |
| `src/pearl/config.py` | All `PEARL_*` env var settings (Pydantic BaseSettings) |
| `src/pearl/api/router.py` | Master router (`/api/v1`) — mounts all 33 route files |
| `src/pearl/api/middleware/auth.py` | JWT + API key validation, public path list |
| `src/pearl/api/middleware/rate_limit.py` | slowapi rate limiting |
| `src/pearl/dependencies.py` | `get_current_user`, `require_role()`, `RequireReviewer` |
| `src/pearl/errors/handlers.py` | Exception handlers + 403 audit logging |
| `src/pearl/workers/registry.py` | Job type → worker class mapping |
| `src/pearl/workers/scheduler.py` | Periodic scan scheduler (Redis distributed lock) |
| `src/pearl/api/routes/stream.py` | SSE real-time events |
| `src/pearl/api/routes/onboarding.py` | Developer onboarding batch file generation |
| `src/pearl_dev/unified_mcp.py` | MCP server (39 tools) |
| `src/pearl/mcp/tools.py` | MCP tool schema definitions |
| `scripts/pearl_bash_guard.py` | PreToolUse Bash guard hook |
| `scripts/pearl_hook_check.py` | Auto-registration hook (called by batch file) |
| `frontend/src/pages/` | 10 React pages: Dashboard, Project, Findings, Approvals, ApprovalDetail, ExceptionReview, Promotion, Reports, Settings, AdminBusinessUnits |
| `deploy/k8s/` | Kubernetes manifests (deployment, service, ingress, HPA, configmap) |
| `deploy/nginx/pearl.conf` | Nginx config with TLS + SSE support |
