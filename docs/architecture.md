# PeaRL Architecture

## 1. System Overview

PeaRL (Policy-enforced Autonomous Risk Layer) is a model-free governance platform that sits between AI agent teams and production environments. It enforces security gates, approval workflows, capability allowances, and compliance checks before any AI-driven change is promoted — deterministically, without LLM calls.

PeaRL governs two delivery tracks:

- **Secure Agent Factories** — human-in-the-loop AI development teams using Claude Code or similar agents. PeaRL gates their output through configurable promotion pipelines.
- **Secure Dark Agent Factories** — fully autonomous agent runs (no persistent human in the loop). PeaRL enforces pre-agreed allowance profiles, SPIRE workload identities, and factory run telemetry. See [`docs/dark-factory-governance.md`](./dark-factory-governance.md) for the full pattern catalogue.

### Hard Constraints

- **Workers are model-free.** All background workers perform deterministic computation only — data transformation, scoring, routing. No LLM calls, no embeddings, no model API calls inside worker code. Model-based analysis belongs to MASS 2.0 (external).
- **Gates route decisions to humans.** When a gate blocks an action, the correct response is `pearl_request_approval`, not routing around the gate.
- **No self-approval.** `decideApproval` and `createException` require the `reviewer` role. Agents receive 403. This is correct behavior, not a failure state.
- **PEARL_LOCAL=1 is a test harness flag.** Agents must never set or assume it.

---

## 2. Component Diagram

```
External Callers              PeaRL Core                         Data Stores
────────────────              ──────────────────────────────     ────────────

                              ┌─────────────────────────────┐
AI Agents                     │   FastAPI REST API           │──▶  PostgreSQL
  └─▶ LiteLLM Proxy ─────────▶│   /api/v1                    │       (primary store)
        (port 4000)           │   Auth: JWT Bearer           │
        tool prefix:          │         X-API-Key header      │──▶  Redis
        PeaRL-pearl_*         │   RBAC: viewer / operator /  │       (job queue)
                              │         admin / reviewer /   │       (SSE pub/sub)
Dashboard (React) ───────────▶│         service_account      │       (scheduler lock)
  (port 5177 host /           │   Middleware: Auth, RateLimit,│
   5173 container)            │              TraceID          │──▶  MinIO / S3
                              └──────────────┬──────────────┘       (report artifacts)
CI/CD / API clients ─────────▶              │
                              ┌──────────────▼──────────────┐
                              │   Background Workers         │
                              │   (Redis job queue)          │
                              │   compile_context            │
                              │   scan_source                │
                              │   mass_scan                  │
                              │   sonar_scan                 │
                              │   normalize_findings          │
                              │   generate_remediation_spec  │
                              │   report                     │
                              └──────────────┬──────────────┘
                                             │
                         ┌───────────────────▼──────────────┐
                         │  External Integrations            │
                         │  MASS 2.0 (AI security scanner)   │
                         │  SonarQube (quality gate)         │
                         │  Snyk / Semgrep / Trivy           │
                         └──────────────────────────────────┘
```

---

## 3. Data Model

### Project / Agent Identity

| Table | Key Fields | Notes |
|---|---|---|
| `OrgRow` | `org_id` | Top-level tenancy boundary |
| `BusinessUnitRow` | `bu_id`, `org_id` | Subdivision within org |
| `UserRow` | `user_id`, `org_id`, `roles` | Human or service user |
| `ApiKeyRow` | `key_id`, `user_id`, `expires_at` | SHA-256 hash stored, not plaintext |
| `ProjectRow` | `project_id`, `org_id`, `bu_id` | One per agent team. Carries `agent_members` (JSON), `goal_id`, `current_environment`, `ai_enabled`, `risk_classification`, `intake_card_id`, `litellm_key_refs`, `memory_policy_refs`, `qualification_packet_id` |
| `OrgBaselineRow` | `baseline_id`, `project_id` | Org-wide security defaults attached to a project |
| `AppSpecRow` | `spec_id`, `project_id` | Components, trust boundaries, data classifications, RAI settings |
| `EnvironmentProfileRow` | `profile_id`, `project_id`, `environment` | Per-project per-environment: `autonomy_mode` (assistive / supervised_autonomous / delegated_autonomous / read_only) |
| `AllowanceProfileRow` | `profile_id`, `agent_type` | Versioned capability profile: `blocked_commands`, `blocked_paths`, `pre_approved_actions`, `model_restrictions`, `budget_cap_usd`, `env_tier_overrides`. Version incremented on every update |
| `AllowanceProfileVersionRow` | `version_id`, `profile_id`, `profile_version` | Snapshot of profile at each version for audit |

### Workload / Execution

| Table | Key Fields | Notes |
|---|---|---|
| `WorkloadRow` | `workload_id`, `svid`, `task_packet_id` | Maps active SPIRE SVIDs to task packets and allowance profiles. Tracks `agent_id`, `last_seen_at`, `status` |
| `TaskPacketRow` | `task_packet_id`, `project_id` | Unit of work. `execution_phase`: planning / coding / testing / review / complete / failed. `phase_history` JSON. Carries `allowed_paths`, `pre_approved_commands`, `allowance_profile_id`, `allowance_profile_version`, `trace_id` |
| `FactoryRunSummaryRow` | `frun_id` (= session_id), `project_id` | Aggregated run telemetry per factory session. Fields: `total_cost_usd`, `models_used`, `tools_called`, `anomaly_flags`, `outcome` (achieved / failed / abandoned), `duration_ms`, `svid`, `goal_id`, `promoted` |
| `RemediationSpecRow` | `spec_id`, `project_id` | Generated remediation specification linked to findings |
| `CompiledPackageRow` | `package_id`, `project_id` | Pre-compiled context snapshot with artifact hashes and policy snapshot |
| `JobRow` | `job_id`, `job_type`, `status` | Tracks async worker jobs. Status: queued / running / succeeded / failed / partial |

### Gate / Promotion

| Table | Key Fields | Notes |
|---|---|---|
| `PromotionGateRow` | `gate_id`, `source_environment`, `target_environment` | Gate definition: `rules` (JSON), `approval_mode`, `auto_pass` (bool), `pass_count`, `auto_pass_threshold` |
| `PromotionEvaluationRow` | `evaluation_id`, `project_id`, `gate_id` | Evaluation result: `rule_results` (JSON), `passed_count`, `failed_count`, `blockers`, `status`, `trace_id`, `commit_sha` |
| `PromotionHistoryRow` | `history_id`, `project_id` | Successful promotion record: `source_environment`, `target_environment`, `promoted_by`, `promoted_at`, `evaluation_id` |
| `PromotionPipelineRow` | `pipeline_id` | Ordered stage list for org or project. `stages` JSON: `[{key, label, order}]` |
| `PolicyVersionRow` | `version_id`, `project_id` | Policy change audit trail |
| `ApprovalRow` | `approval_id`, `project_id` | Approval request + decision. `status`: pending / approved / rejected / expired / needs_info |
| `ExceptionRow` | `exception_id`, `project_id` | Policy exception. `status`: pending / active / expired / revoked / rejected |

### Findings / Compliance

| Table | Key Fields | Notes |
|---|---|---|
| `FindingRow` | `finding_id`, `project_id` | Security finding. `severity`, `status` (open / resolved / false_positive / accepted / suppressed), `category` (security / responsible_ai / governance / architecture_drift) |
| `FairnessCaseRow` | `case_id`, `project_id` | RAI risk tier, fairness criticality |
| `EvidencePackageRow` | `evidence_id`, `project_id` | Evidence attestation: `evidence_type`, `attestation_status`, `expires_at` |
| `OrgEnvConfigRow` | `config_id`, `project_id` | Per-environment policy overrides |
| `ScanTargetRow` | `target_id`, `project_id` | Registered scan targets for periodic scanning |
| `ScannerPolicyRow` | `policy_id` | Scanner-identified policy store |
| `CedarDeploymentRow` | `deployment_id`, `project_id` | Cedar policy deployment records |
| `AuditEventRow` | `event_id`, `project_id` | HMAC-signed immutable audit record |

### Telemetry / Audit

| Table | Key Fields | Notes |
|---|---|---|
| `ClientAuditEventRow` | `event_id`, `project_id` | Agent-pushed audit events: `action`, `decision`, `tool_name`, `reason`, `signature` (HMAC) |
| `ClientCostEntryRow` | `entry_id`, `project_id` | Per-LLM-call cost: `session_id`, `model`, `cost_usd`, `tools_called`, `num_turns`, `duration_ms` |

---

## 4. Promotion Pipeline

### Pipeline Stages

The default pipeline is stored in `PromotionPipelineRow` as an ordered stage list. The three primary stages are:

```
pilot  →  dev  →  prod
```

Each transition has a `PromotionGateRow` defining the rules that must pass. The evaluator resolves the next stage dynamically from the pipeline record using `next_environment()`.

### Gate Evaluation Flow

```
POST /projects/{id}/promotions/evaluate
  │
  ▼
evaluate_promotion()  [src/pearl/services/promotion/gate_evaluator.py]
  │
  ├── Load ProjectRow → determine current_environment
  ├── Load PromotionGateRow for (source → target) transition
  ├── _build_eval_context()
  │     Loads: findings, approvals, fairness cases, evidence packages,
  │            compiled packages, org baseline, scan results, MASS verdicts
  │
  ├── For each GateRuleDefinition in gate.rules:
  │     RULE_EVALUATORS[rule_type](context) → RuleEvaluationResult (pass/fail/skip/warn/exception)
  │
  ├── Persist PromotionEvaluationRow
  │
  └── Return PromotionEvaluation
        status: passed | failed | partial | not_evaluated
        passed_count, failed_count, blockers
```

### Trust Accumulation

`PromotionGateRow` carries trust accumulation fields:
- `pass_count` — incremented each time the gate passes cleanly
- `auto_pass_threshold` — number of consecutive passes required before auto-pass unlocks
- `auto_pass` — when true, gates that have earned trust may be skipped on re-evaluation

Auto-pass behavior in gate re-evaluation:
- `auto_pass=False` (manual mode): a re-evaluation failure is a hard block. Must raise, never silently pass.
- `auto_pass=True` (auto-elevation mode): a re-evaluation failure logs a warning and continues.

### Human Approval at Gates

When a gate evaluation fails, agents must call `pearl_request_approval`. The approval workflow:

```
POST /approvals (create)
  → ApprovalRow status=pending

POST /approvals/{id}/decide (reviewer role required)
  → ApprovalRow status=approved|rejected
  → SSE event published
  → Gate re-evaluated if approved
```

Agents receive 403 on `/decide` — this is the intended control. Routing around this is never correct.

---

## 5. Gate Rule Categories

| Category | Rules | Description |
|---|---|---|
| **Base Security** | `PROJECT_REGISTERED`, `ORG_BASELINE_ATTACHED`, `APP_SPEC_DEFINED`, `NO_HARDCODED_SECRETS`, `UNIT_TESTS_EXIST`, `UNIT_TEST_COVERAGE`, `INTEGRATION_TEST_COVERAGE`, `SECURITY_BASELINE_TESTS`, `CRITICAL_FINDINGS_ZERO`, `HIGH_FINDINGS_ZERO`, `DATA_CLASSIFICATIONS_DOCUMENTED`, `IAM_ROLES_DEFINED`, `NETWORK_BOUNDARIES_DECLARED`, `ALL_CONTROLS_VERIFIED`, `SECURITY_REVIEW_APPROVAL`, `EXEC_SPONSOR_APPROVAL`, `RESIDUAL_RISK_REPORT`, `READ_ONLY_AUTONOMY`, `SCAN_TARGET_REGISTERED` | Traditional project security hygiene gates |
| **AI-Specific** | `AI_SCAN_COMPLETED`, `NO_PROMPT_INJECTION`, `GUARDRAILS_VERIFIED`, `NO_PII_LEAKAGE`, `OWASP_LLM_TOP10_CLEAR`, `AI_RISK_ACCEPTABLE`, `COMPREHENSIVE_AI_SCAN`, `LITELLM_COMPLIANCE`, `FACTORY_RUN_SUMMARY_PRESENT`, `MODEL_CARD_DOCUMENTED`, `RAI_EVAL_COMPLETED` | AI deployment readiness. `LITELLM_COMPLIANCE` verifies gateway configuration; `FACTORY_RUN_SUMMARY_PRESENT` requires at least one `FactoryRunSummaryRow` for the project before promotion |
| **OWASP LLM Top 10** | `OWASP_LLM05_IMPROPER_OUTPUT_HANDLING`, `OWASP_LLM06_EXCESSIVE_AGENCY`, `OWASP_LLM07_SYSTEM_PROMPT_LEAKAGE`, `OWASP_LLM08_VECTOR_WEAKNESSES`, `OWASP_LLM10_UNBOUNDED_CONSUMPTION` | Per-control discrete rules from OWASP LLM Top 10 v2025 |
| **NHI (Non-Human Identity)** | `NHI_IDENTITY_REGISTERED`, `NHI_SECRETS_IN_VAULT`, `NHI_CREDENTIAL_ROTATION_POLICY`, `NHI_LEAST_PRIVILEGE_VERIFIED`, `NHI_TOKEN_EXPIRY_CONFIGURED` | Agent credential governance — SPIRE SVID registration, vault storage, rotation policy, expiry |
| **Agent Governance** | `AGENT_CAPABILITY_SCOPE_DOCUMENTED`, `AGENT_KILL_SWITCH_IMPLEMENTED`, `AGENT_BLAST_RADIUS_ASSESSED`, `AGENT_COMMUNICATION_SECURED` | Operational controls for autonomous agents |
| **Supply Chain** | `SBOM_GENERATED`, `SNYK_OPEN_HIGH_CRITICAL`, `SONARQUBE_QUALITY_GATE` | Software supply chain and third-party dependency gates |
| **Fairness** | `FAIRNESS_CASE_DEFINED`, `FAIRNESS_REQUIREMENTS_MET`, `FAIRNESS_EVIDENCE_CURRENT`, `FAIRNESS_ATTESTATION_SIGNED`, `FAIRNESS_HARD_BLOCKS_CLEAR`, `FAIRNESS_DRIFT_ACCEPTABLE`, `FAIRNESS_CONTEXT_RECEIPT_VALID`, `FAIRNESS_EXCEPTIONS_CONTROLLED`, `FAIRNESS_POLICY_DEPLOYED`, `CEDAR_POLICY_DEPLOYED` | FEU-sourced responsible AI requirements |
| **Framework Controls** | `FRAMEWORK_CONTROL_REQUIRED`, `AIUC1_CONTROL_REQUIRED` | Unified framework gate covering AIUC-1, OWASP LLM/Web, MITRE ATLAS, SLSA, NIST RMF/SSDF |
| **Governance** | `CLAUDE_MD_GOVERNANCE_PRESENT`, `COMPLIANCE_SCORE_THRESHOLD`, `REQUIRED_ANALYZERS_COMPLETED`, `GUARDRAIL_COVERAGE`, `SECURITY_REVIEW_CLEAR` | Governance process attestation |

---

## 6. MCP Integration

### Transport and Naming

PeaRL exposes MCP governance tools via `POST /api/v1/mcp`. The MCP server is in `src/pearl_dev/unified_mcp.py`; tool schemas are in `src/pearl/mcp/tools.py`.

All tool names carry the `pearl_` prefix so agents can unambiguously distinguish PeaRL tools when multiple MCP servers are loaded.

In LiteLLM, tools appear as `PeaRL-pearl_*` (server name prefix + tool name).

### Agent Integration Flow

```
Agent (Claude Code)
  └─▶ LiteLLM Proxy (localhost:4000)
        X-API-Key: sk-litellm-local-testing
        │
        └─▶ PeaRL API (/api/v1/mcp)
              X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk
              │
              └─▶ PostgreSQL / Redis / Workers
```

LiteLLM forwards the PeaRL API key via `X-API-Key` header. PeaRL validates it against `ApiKeyRow` using a SHA-256 hash lookup.

### Tool Catalogue

| Category | Tools |
|---|---|
| **Project Management** | `pearl_register_project`, `pearl_create_project`, `pearl_get_project`, `pearl_update_project`, `pearl_get_project_summary`, `pearl_list_projects` |
| **Project Configuration** | `pearl_upsert_org_baseline`, `pearl_upsert_application_spec`, `pearl_upsert_environment_profile` |
| **Context** | `pearl_compile_context`, `pearl_get_compiled_package`, `pearl_submit_context_receipt` |
| **Findings & Remediation** | `pearl_ingest_findings`, `pearl_generate_remediation_spec`, `pearl_generate_task_packet`, `pearl_claim_task_packet`, `pearl_complete_task_packet`, `pearl_list_findings` |
| **Governance** | `pearl_request_approval`, `pearl_decide_approval`, `pearl_create_exception`, `pearl_request_promotion`, `pearl_evaluate_promotion_readiness`, `pearl_get_promotion_readiness`, `pearl_get_promotion_history` |
| **Compliance & Fairness** | `pearl_create_fairness_case`, `pearl_submit_evidence`, `pearl_assess_compliance`, `pearl_list_guardrails`, `pearl_get_guardrail`, `pearl_get_recommended_guardrails`, `pearl_get_recommended_baseline`, `pearl_apply_recommended_baseline`, `pearl_list_policy_templates`, `pearl_get_policy_template`, `pearl_ingest_security_review` |
| **Scanning** | `pearl_register_scan_target`, `pearl_list_scan_targets`, `pearl_update_scan_target`, `pearl_run_scan`, `pearl_get_scan_results` |
| **Workload Registry** | `pearl_register_workload`, `pearl_update_workload`, `pearl_deregister_workload`, `pearl_get_workload` |
| **Factory Run** | `pearl_push_factory_run_summary`, `pearl_get_factory_run_summary` |
| **Allowance Profiles** | `pearl_get_allowance_profile`, `pearl_list_allowance_profiles` |
| **Monitoring & Jobs** | `pearl_ingest_monitoring_signal`, `pearl_get_job_status` |
| **Reports** | `pearl_generate_report` |

### Governance-Sensitive Tools

`pearl_decide_approval` and `pearl_create_exception` are gated: the underlying endpoints require the `reviewer` role. Agents calling these tools receive a 403 with `_human_action_required: true` and a dashboard URL. The agent cannot self-approve — it must surface the action to a human reviewer.

---

## 7. Agent Team Model

### Project as Team Container

One `ProjectRow` per agent team. Key fields for Dark Factory integration:

- `agent_members` (JSON) — list of agent identifiers participating in this project
- `goal_id` — links the project to a WTK intake card goal
- `current_environment` — tracks which pipeline stage the project is currently in
- `intake_card_id` — WTK intake card reference
- `litellm_key_refs` — references to LiteLLM virtual keys issued to this team
- `memory_policy_refs` — memory boundary policy references
- `qualification_packet_id` — pre-qualification attestation

### Workload Registry

Each active agent instance registers a `WorkloadRow` with a SPIRE SVID. This ties the identity to a specific task packet and allowance profile version. The registry is the enforcement anchor for NHI gate rules — `NHI_IDENTITY_REGISTERED` fails if no workload row exists for the agent.

### Factory Run Summary Materialization

`FactoryRunSummaryRow` is materialized from `ClientCostEntryRow` records using the `session_id` as the grouping key (`frun_id`). Two triggers fire the upsert: workload deregister and task packet complete. The upsert is idempotent — both triggers can fire without creating duplicates. The `FACTORY_RUN_SUMMARY_PRESENT` gate rule checks for at least one summary row before allowing promotion.

---

## 8. Background Workers

All workers extend `BaseWorker` and are registered in `src/pearl/workers/registry.py`. Workers perform deterministic computation only — no LLM calls, no embeddings.

| Job Type | Worker Class | Purpose |
|---|---|---|
| `compile_context` | `CompileContextWorker` | Builds compiled context package with artifact hashes and policy snapshot |
| `scan_source` | `ScanWorker` | Local path scan for security findings |
| `mass_scan` | `MassScanWorker` | Calls MASS 2.0 external scanner via `MassClient`; stores verdicts as findings |
| `sonar_scan` | `SonarScanWorker` | Calls SonarQube API; maps quality gate result to `SONARQUBE_QUALITY_GATE` rule |
| `normalize_findings` | `NormalizeFindingsWorker` | Sets `normalized=True`, assigns score and severity on raw ingested findings |
| `generate_remediation_spec` | `GenerateRemediationWorker` | Produces deterministic remediation spec from finding data |
| `report` | `GenerateReportWorker` | Assembles report artifact and uploads to MinIO/S3 |

### Worker Execution

```
Redis List: pearl:jobs:{job_type}
  │
  ▼
Worker process (asyncio)
  ├── Pop job
  ├── Update JobRow status → running
  ├── Call BaseWorker.process(job_id, payload, session) → result
  │     On success: status → succeeded, result_refs set
  │     On error:   retry up to max_retries=3, then failed
  └── Commit to DB
```

Periodic scans are enqueued by the scheduler (`src/pearl/workers/scheduler.py`), which polls scan targets every 60 seconds using a Redis distributed lock to prevent duplicate enqueues.

---

## 9. Auth and RBAC

### Auth Flow

```
Request
  │
  ▼
AuthMiddleware  [src/pearl/api/middleware/auth.py]
  ├── Bearer <token>   → JWT decode (python-jose)
  │     HS256  — PEARL_LOCAL=1 / local dev
  │     RS256  — production (PEARL_JWT_ALGORITHM=RS256)
  │
  ├── X-API-Key: <key> → SHA-256 hash lookup → ApiKeyRow → UserRow
  │     Validates: is_active, expires_at; updates last_used_at
  │
  └── No credential → anonymous (health, login, jwks pass through)
        │
        ▼
  request.state.user = {sub, roles, scopes, email}
```

### Roles

| Role | Granted Capabilities |
|---|---|
| `viewer` | Read-only access to project data |
| `operator` | Create projects, ingest findings, generate task packets, request approvals and promotions |
| `admin` | All operator capabilities plus user management, rollback, org config |
| `reviewer` | Decide approvals and exceptions, mark false positives. Cannot be self-granted by agents |
| `service_account` | Automated CI/CD integration; scoped to specific project |

`PEARL_LOCAL=1` grants `operator` only. Reviewer-mode local dev requires `PEARL_LOCAL_REVIEWER=1` set explicitly by a human.

### Reviewer-Gated Endpoints

| Endpoint | Gate |
|---|---|
| `POST /approvals/{id}/decide` | `RequireReviewer` |
| `POST /exceptions/{id}/decide` | `RequireReviewer` |
| `PATCH /projects/{id}/findings/{id}/status` (false_positive) | `RequireReviewer` |
| `POST /projects/{id}/findings/bulk-status` (false_positive) | `RequireReviewer` |

`REVIEWER_ROLES = ("security_reviewer", "security_analyst", "security_manager", "governance", "admin")`

---

## 10. Deployment

### Docker Compose Stack

| Service | Image | Ports | Notes |
|---|---|---|---|
| `pearl-api` | Local build | `8080:8080` | FastAPI + workers. Connects to postgres, redis, minio |
| `frontend` | Local build (dev target) | `5177:5173` | React/Vite. `VITE_API_BASE_URL` points to pearl-api |
| `postgres` | `postgres:16` | `5433:5432` | Primary store. healthcheck: `pg_isready -U pearl` |
| `redis` | `redis:7` | `6379:6379` | Job queue, SSE pub/sub, scheduler lock |
| `minio` | `minio/minio` | `9000:9000`, `9001:9001` | Report artifact storage. Console at 9001 |
| `sonarqube` | `sonarqube:community` | `9090:9000` | Quality gate. Shares postgres (database: sonar) |
| `sonar-scanner` | `sonarsource/sonar-scanner-cli` | — | Profile `scan` only; run manually: `docker compose run --rm sonar-scanner` |

### Key Environment Variables (pearl-api)

| Variable | Default | Purpose |
|---|---|---|
| `PEARL_DATABASE_URL` | `postgresql+asyncpg://pearl:pearl@postgres:5432/pearl` | Primary DB |
| `PEARL_REDIS_URL` | `redis://redis:6379/0` | Redis |
| `PEARL_S3_ENDPOINT_URL` | `http://minio:9000` | Artifact storage |
| `PEARL_JWT_SECRET` | `dev-secret-change-in-production` | JWT signing key |
| `PEARL_JWT_ALGORITHM` | `HS256` | HS256 local, RS256 prod |
| `PEARL_MASS_URL` | `http://host.docker.internal:80` | MASS 2.0 base URL |
| `PEARL_LITELLM_API_URL` | `http://host.docker.internal:4000` | LiteLLM proxy URL |
| `PEARL_LOCAL_REVIEWER_MODE` | `1` | Enables reviewer role in Docker compose stack |
| `PEARL_SONAR_URL` | `http://localhost:9090` | SonarQube API base |

### Local Dev (PEARL_LOCAL=1)

`PEARL_LOCAL=1` switches to SQLite in-memory, bypasses auth middleware, and auto-creates tables via metadata. No Alembic migrations needed. Use for unit tests only:

```bash
PEARL_LOCAL=1 pytest tests/ -q
```

Schema changes must go through Alembic migrations in `src/pearl/db/migrations/versions/`. Do not add `ALTER TABLE` calls to the lifespan.

### Production Kubernetes

Kubernetes manifests are in `deploy/k8s/` (deployment, service, ingress, HPA, configmap). Nginx config with TLS and SSE support is in `deploy/nginx/pearl.conf`.

---

## 11. Observability

| Signal | Implementation |
|---|---|
| Structured logs | `structlog` — JSON in production, console in local |
| Request tracing | `X-Trace-ID` header via TraceID middleware → `request.state.trace_id` → stored on evaluation and task packet rows |
| Governance access denied | `WARNING governance_access_denied` on every 403 `AuthorizationError` (path, user_sub, roles, trace_id) |
| Behavioral anomaly detection | `WARNING governance_anomaly_detected` emitted post-response by `src/pearl/security/anomaly_detector.py` for AGP-01–05 patterns |
| Metrics | Prometheus via `prometheus-fastapi-instrumentator` at `GET /metrics` |
| Health probes | `GET /health/live` (always 200), `GET /health/ready` (checks DB SELECT 1 + Redis PING; 503 if either fails) |
| Client telemetry | Agents push audit events via `POST /projects/{id}/audit-events` and cost entries via `POST /projects/{id}/cost-entries` (batch, max 500 each) |
| Real-time SSE | `GET /stream/events` — Redis pub/sub backend. Events on: approval created/decided, gate failure, finding batch ingested, task packet claimed/completed, promotion requested |

---

## 12. Key Files Reference

| File | Purpose |
|---|---|
| `src/pearl/main.py` | App factory, lifespan, middleware registration |
| `src/pearl/config.py` | All `PEARL_*` env var settings (Pydantic BaseSettings) |
| `src/pearl/api/router.py` | Master router (`/api/v1`) |
| `src/pearl/api/middleware/auth.py` | JWT + API key validation |
| `src/pearl/api/middleware/rate_limit.py` | slowapi rate limiting |
| `src/pearl/dependencies.py` | `get_current_user`, `require_role()`, `RequireReviewer` |
| `src/pearl/errors/handlers.py` | Exception handlers + 403 audit logging |
| `src/pearl/models/enums.py` | All string enums (GateRuleType, AutonomyMode, ExecutionPhase, etc.) |
| `src/pearl/services/promotion/gate_evaluator.py` | Deterministic gate evaluation engine |
| `src/pearl/workers/registry.py` | Job type → worker class mapping |
| `src/pearl/workers/scheduler.py` | Periodic scan scheduler (Redis distributed lock, 60s) |
| `src/pearl/api/routes/stream.py` | SSE real-time events |
| `src/pearl/mcp/tools.py` | MCP tool schema definitions |
| `src/pearl_dev/unified_mcp.py` | MCP server — handles `/api/v1/mcp` |
| `src/pearl/security/anomaly_detector.py` | Post-response AGP-01–05 behavioral anomaly detection |
| `src/pearl/db/migrations/versions/` | Alembic migration files (001–011) |
| `deploy/k8s/` | Kubernetes manifests |
| `deploy/nginx/pearl.conf` | Nginx config with TLS + SSE support |
| `docs/dark-factory-governance.md` | Dark Factory governance pattern catalogue (P-01–P-13) |
