# PeaRL Architecture

## System Overview

PeaRL enforces governance between AI agents and production environments. It acts as a policy layer that:

1. Compiles risk context from project metadata + findings + policies
2. Evaluates promotion readiness through configurable gates
3. Orchestrates approval workflows (human or automated)
4. Executes remediation tasks via agent task packets
5. Audits all actions for compliance

## Component Diagram

```
External Systems          PeaRL Core                    Data Stores
─────────────────         ──────────────────────────    ────────────
                          ┌────────────────────────┐
AI Agents (MCP)  ────────▶│   FastAPI REST API     │──▶  PostgreSQL
                          │   /api/v1              │
Claude/Codex     ────────▶│   Auth: JWT / API Key  │──▶  Redis
                          │   RBAC: roles          │        (jobs + SSE)
CI/CD systems    ────────▶│   CORS: configurable   │
                          └─────────┬──────────────┘
                                    │
                          ┌─────────▼──────────────┐
Scanners                  │   Background Workers    │──▶  MinIO (S3)
 Snyk / Semgrep ─────────▶│   scan_source           │       (reports)
 Trivy          ─────────▶│   normalize_findings    │
                          │   generate_remediation  │
                          │   report                │
                          └─────────┬──────────────┘
                                    │
Governance                ┌─────────▼──────────────┐
 Approvals ◀──────────────│   Scheduler             │
 Exceptions               │   (60s poll, Redis lock)│
 Audit trail              └────────────────────────┘
```

## Data Flow

### Finding Ingestion Flow
```
Scanner → POST /findings/ingest → FindingBatch + FindingRows
                                       ↓
                               normalize_findings job
                                       ↓
                         FindingRow.normalized=True, score set
```

### Promotion Flow
```
POST /promotions/evaluate
  → GateEvaluator checks rules (findings, approvals, fairness)
  → PromotionEvaluationRow with pass/fail per rule
  → If all pass: POST /promotions/request → PromotionHistoryRow
  → If blocked: requires human approval via /approvals
```

### Agent Task Packet Flow
```
POST /projects/{id}/task-packets (generate)
  → Compile context + remediation spec
  → TaskPacketRow created

POST /task-packets/{id}/claim  (agent claims)
  → agent_id, claimed_at set

Agent executes changes

POST /task-packets/{id}/complete (agent reports)
  → outcome recorded
  → resolved findings marked status="resolved"
  → governance telemetry event created
```

## Database Schema (Key Relationships)

```
OrgRow
  └─▶ UserRow (org_id)
  └─▶ ProjectRow (org_id)
       └─▶ OrgBaselineRow
       └─▶ AppSpecRow
       └─▶ EnvironmentProfileRow
       └─▶ FindingRow
       │    └─▶ FindingBatchRow
       └─▶ ApprovalRequestRow
       │    └─▶ ApprovalDecisionRow
       │    └─▶ ApprovalCommentRow
       └─▶ ExceptionRecordRow
       └─▶ TaskPacketRow
       └─▶ RemediationSpecRow
       └─▶ ReportRow
       └─▶ JobRow
       └─▶ ScanTargetRow
       └─▶ PromotionHistoryRow
       └─▶ PolicyVersionRow
```

## Auth Architecture

```
Request
  │
  ▼
AuthMiddleware
  ├─ Bearer <token> → JWT decode (python-jose)
  │    ├─ HS256 (local dev)
  │    └─ RS256 / OIDC (production)
  │
  ├─ X-API-Key: pk_... → SHA-256 hash lookup → ApiKeyRow → UserRow
  │
  └─ No auth → anonymous (some routes allow, most require auth)
       │
       ▼
  request.state.user = {sub, roles, scopes, email}
       │
       ▼
  Route handler: Depends(get_current_user) or Depends(require_role("admin"))
```

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
  │    └─ On error: retry up to max_retries (3), then "failed"
  └─ Commit to DB

Worker Registry:
  "compile_context"        → CompileContextWorker
  "scan_source"            → ScanWorker
  "normalize_findings"     → NormalizeFindingsWorker
  "generate_remediation_spec" → GenerateRemediationWorker
  "report"                 → GenerateReportWorker
```

## Real-Time Events

SSE is served at `GET /stream/events`. Redis pub/sub is the backend:

```
API route creates event → redis.publish("pearl:events:broadcast", json)
                                           │
API route creates user event → redis.publish("pearl:events:user:{id}", json)
                                           │
                                      SSE endpoint
                                      GET /stream/events
                                           │
                                      Browser EventSource
```

Events published on:
- Approval creation/decision
- Gate failure
- Finding batch ingestion
- Task packet completion
