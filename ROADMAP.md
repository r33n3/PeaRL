# PeaRL Gap Remediation Roadmap

## Priority Framework
- **P0 (Critical)**: Blocks production use or creates unacceptable risk
- **P1 (High)**: Limits core value proposition; needed before pilot users
- **P2 (Medium)**: Important for scale, reliability, and developer experience
- **P3 (Low)**: Nice-to-have; improves polish and long-term maintainability

---

## Phase 1: Foundation & Security (P0)
_Goal: Make PeaRL safe to run beyond localhost_

### 1.1 User & Identity Management
- Add user/team/org tables and RBAC model
- Define roles: viewer, operator, admin, service-account
- Wire roles into existing auth middleware
- **Why first**: Every other feature (approvals, audit, multi-tenancy) depends on knowing _who_ is acting

### 1.2 Auth Upgrade
- Add RS256 JWT support (asymmetric signing)
- OAuth2/OIDC integration (SSO via GitHub, Azure AD, Okta)
- API key management for service-to-service auth
- Token refresh and rotation
- **Why first**: HS256 shared-secret is unsuitable for any multi-service deployment

### 1.3 CI/CD Pipeline
- GitHub Actions workflow: lint (ruff) → test (pytest) → build (Docker) → publish
- Contract validation against OpenAPI spec
- Branch protection on main
- **Why first**: All subsequent work needs automated quality gates

### 1.4 TLS & CORS Configuration
- Reverse proxy config (nginx/Caddy) or cloud load balancer template
- Dynamic CORS origin from environment variable
- **Why first**: Prerequisite for any non-local deployment

---

## Phase 2: Close the Execution Loop (P1)
_Goal: PeaRL doesn't just describe risk — it acts on it_

### 2.1 Scanner Orchestration
- Implement scan execution (not just finding ingestion) for Semgrep, Snyk, Trivy
- Scan job scheduling via the existing worker/job queue
- Webhook receivers for scan-complete callbacks
- **Why**: Core value prop — without scan execution, findings must be pushed in externally

### 2.2 Background Worker Buildout
- Implement workers for: normalize_findings, generate_remediation_spec, report
- Job retry logic with exponential backoff
- Dead-letter handling for failed jobs
- **Why**: Only compile worker exists; the job queue is underutilized

### 2.3 Remediation Execution Bridge
- Agent execution adapter that consumes task packets
- Feedback loop: agent reports outcome → finding status updated
- Guard rails enforcement during execution
- **Why**: Closes the loop from finding → remediation spec → task packet → fix → verification

### 2.4 Production Deployment Target
- Kubernetes manifests (or Docker Swarm / ECS task definitions)
- Helm chart or Kustomize overlays for env-specific config
- Secrets management integration (Vault, AWS Secrets Manager, or sealed-secrets)
- Health/readiness/liveness probes
- **Why**: Docker Compose is dev-only; need a production-grade deployment path

---

## Phase 3: Operational Maturity (P2)
_Goal: Reliable, observable, and scalable for real teams_

### 3.0 Developer Experience — Scan & Gate Stability (P1 bump)

#### 3.0.1 Compiled Context Package Persistence
- Compiled context package (`.pearl/compiled-context-package.json`) is wiped on every Claude Code restart
- Should persist and only recompile when project inputs actually change (baseline, app spec, environment profile)
- Add `last_compiled_at` + input hash to compiled package; skip recompile if inputs unchanged
- Gate scores currently fluctuate between sessions because missing package causes rules to fall back to "not evaluated = fail"
- **Why**: Gate scores should be stable across sessions — recompilation should be triggered by data changes, not session restarts

#### 3.0.2 MCP Response Size Limits
- Large findings payloads (1M+ chars) cause token limit errors when Claude pulls full finding objects
- Add `limit` and `severity` filter params to `getFindings` MCP tool
- Add `GET /projects/{id}/findings/summary` endpoint returning counts by severity + top 5 critical only
- Cap any single MCP tool response at ~50KB with `truncated: true` flag and filter hint
- **Why**: Prevents silent failures and context window blowout on larger projects

#### 3.0.3 Scan Scope Exclusions (.pearlignore)
- Scans currently include `.venv`, `node_modules`, `__pycache__` causing false positive critical findings
- Add `.pearlignore` file support (gitignore-style) to scan target evaluation
- Default exclusions: `.venv/`, `node_modules/`, `__pycache__/`, `*.pyc`, `.git/`
- **Why**: False positives from third-party packages pollute findings and block gate promotion on noise

#### 3.0.4 Onboarding Setup Endpoint
- `GET /api/v1/onboarding/setup` returns pre-configured `Claude Code.bat` + instructions JSON
- Batch file auto-writes `.mcp.json` with correct python path and API URL for any new project
- Eliminates manual MCP configuration for new developers
- **Why**: Current manual setup causes MCP connection failures (wrong port, wrong python path)

#### 3.0.5 MCP Tool Profiles & Role-Gated API Access
- `unified_mcp --profile <developer|reviewer|admin>` already implemented (Feb 2026)
- `developer` profile (default): hides `decideApproval`, `upsertOrgBaseline`, `upsertApplicationSpec`, `upsertEnvironmentProfile`, `applyRecommendedBaseline`
- `reviewer` / `admin` profiles: full tool exposure (requires JWT with reviewer role in production)
- `POST /approvals/{id}/decide` and `POST /exceptions/{id}/decide` are role-gated to `security_reviewer | security_analyst | security_manager | governance | admin`
- **Future**: Dedicated reviewer `.mcp.json` profile for security analysts who want Claude-assisted review workflows in their own chat tool
- **Future**: Per-project tool allowlist stored in org-baseline — override default profile per environment
- **Why**: Prevents agents from self-approving security exceptions; governance decisions stay with human reviewers


_Goal: Reliable, observable, and scalable for real teams_

### 3.1 Rate Limiting & API Protection
- Rate limiting middleware (per-user, per-endpoint)
- Request size limits
- Input sanitization hardening

### 3.2 Real-Time Notifications
- WebSocket or SSE endpoint for live dashboard updates
- Push notifications for approval requests and gate failures
- Reduce polling dependency in frontend

### 3.3 Policy Versioning & Audit
- Version history for org-baselines, app-specs, environment-profiles
- Diff view between policy versions
- Change attribution (who changed what, when)

### 3.4 Promotion Rollback
- Demotion/rollback mechanism for failed promotions
- Rollback audit trail
- Automatic rollback triggers on critical finding detection

### 3.5 Observability
- Structured logging (JSON) with correlation via trace_id
- Metrics export (Prometheus endpoint or OpenTelemetry)
- Dashboard for API latency, error rates, job queue depth

### 3.6 Multi-Tenancy Foundation
- Org-scoped data isolation
- Tenant-aware queries across all repositories
- Org-level admin vs project-level roles

---

## Phase 4: Quality & Developer Experience (P3)
_Goal: Sustainable development velocity and contributor onboarding_

### 4.1 Documentation
- README.md with quickstart, architecture overview, and local dev setup
- CLAUDE.md with project conventions for AI-assisted development
- CONTRIBUTING.md with PR workflow and coding standards
- API documentation portal (Swagger UI customization or Redoc)

### 4.2 Frontend Testing
- Playwright or Cypress e2e test suite for critical flows
- Component tests for key UI elements
- Visual regression testing

### 4.3 Load & Performance Testing
- k6 or Locust scripts for key API paths
- Baseline performance metrics
- Database query optimization (N+1 detection, index review)

### 4.4 Contract Testing Automation
- Automated OpenAPI spec ↔ implementation drift detection in CI
- Schema validation for all example payloads in PeaRL_spec/

---

## Suggested Execution Order

```
Phase 1 (Foundation)          Phase 2 (Execution)
┌─────────────────────┐      ┌─────────────────────┐
│ 1.3 CI/CD           │─────▶│ 2.2 Workers          │
│ 1.1 Users & RBAC    │─────▶│ 2.1 Scanner Orch     │
│ 1.2 Auth Upgrade     │─────▶│ 2.3 Remediation Exec │
│ 1.4 TLS & CORS      │─────▶│ 2.4 Prod Deployment  │
└─────────────────────┘      └─────────────────────┘
         ▼                            ▼
Phase 3 (Operations)          Phase 4 (Quality)
┌─────────────────────┐      ┌─────────────────────┐
│ 3.1 Rate Limiting    │      │ 4.1 Documentation    │
│ 3.2 Real-Time Notif  │      │ 4.2 Frontend Tests   │
│ 3.3 Policy Versioning│      │ 4.3 Perf Testing     │
│ 3.4 Rollback         │      │ 4.4 Contract Tests   │
│ 3.5 Observability    │      └─────────────────────┘
│ 3.6 Multi-Tenancy    │
└─────────────────────┘
```

Within each phase, items are listed in recommended order. Phase 1 items can
largely be parallelized. Phase 2 items have dependencies (workers before
scanner orch; auth before prod deployment). Phases 3 and 4 can overlap.

---

## Quick Wins (Can Start Immediately)
- [ ] 1.3 CI/CD — GitHub Actions with ruff + pytest (< 1 session)
- [ ] 1.4 CORS from env var (single-line config change)
- [ ] 4.1 README.md (captures what we already know)
- [ ] 3.5 Structured logging (swap print→structlog, leverage existing trace_id)
