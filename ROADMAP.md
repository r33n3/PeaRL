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
