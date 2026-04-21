# PeaRL API — Getting Started

Practical guide to the most important PeaRL API endpoints. This is not an exhaustive reference — it covers what you need to get data in and out and understand common patterns.

---

## 1. Base URL and Auth

**Base URL:** `http://localhost:8080/api/v1`

All requests require authentication. Two options:

**API key (recommended for agents and automation):**
```
X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk
```

**JWT Bearer token (for user sessions):**
```
Authorization: Bearer <token>
```

Obtain a JWT token via `POST /api/v1/auth/login`:
```bash
curl -X POST http://localhost:8080/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pearl.dev","password":"PeaRL-admin-2026"}'
```

Response includes `access_token` (short-lived) and `refresh_token`. Use `POST /api/v1/auth/refresh` with the refresh token to renew.

**Roles:** `viewer`, `operator`, `admin`, `service_account`, `reviewer`. Most write operations require `operator` or above. Approval decisions require `reviewer`.

---

## 2. Projects

Projects are the top-level governance unit. One project = one agent team or application.

**Get a project:**
```bash
curl http://localhost:8080/api/v1/projects/proj_myapp001 \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"
```

Response:
```json
{
  "project_id": "proj_myapp001",
  "name": "My First Project",
  "owner_team": "platform-team",
  "business_criticality": "moderate",
  "external_exposure": "internal_only",
  "ai_enabled": true,
  "current_environment": "pilot",
  "created_at": "2026-04-01T10:00:00Z"
}
```

**Register a new project:**
```bash
curl -X POST http://localhost:8080/api/v1/projects/register \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Agent Team",
    "owner_team": "ape-team",
    "business_criticality": "moderate",
    "external_exposure": "internal_only",
    "ai_enabled": true
  }'
```

The response includes `project_id`, `pearl_yaml` (content to write to `.pearl.yaml`), and `compiled_package` (content to write to `.pearl/compiled-context-package.json`). Write these files before using other tools against this project.

**List projects:**
```bash
curl http://localhost:8080/api/v1/projects \
  -H "X-API-Key: <key>"
```

---

## 3. Gate Evaluation

Gate evaluation checks whether a project is ready to promote to the next environment. PeaRL resolves the current environment from the project record — no body is required for a basic evaluation.

```bash
curl -X POST http://localhost:8080/api/v1/projects/proj_myapp001/promotions/evaluate \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  -H "Content-Type: application/json" \
  -d '{}'
```

Response shape:
```json
{
  "evaluation_id": "eval_abc123",
  "project_id": "proj_myapp001",
  "status": "blocked",
  "source_environment": "pilot",
  "target_environment": "dev",
  "passed": 3,
  "total": 8,
  "progress_pct": 37,
  "blockers": [
    {
      "rule_type": "AI_SCAN_COMPLETED",
      "message": "No AI security scan on record for pilot.",
      "fix_guidance": "Call pearl_run_scan or pearl_trigger_mass_scan to complete a scan."
    },
    {
      "rule_type": "NO_CRITICAL_FINDINGS",
      "message": "1 open critical finding must be resolved.",
      "fix_guidance": "Resolve or obtain an approved exception for all critical findings."
    }
  ],
  "passing_rules": [
    { "rule_type": "CLAUDE_MD_GOVERNANCE_PRESENT" },
    { "rule_type": "ENV_PROFILE_CONFIGURED" },
    { "rule_type": "ORG_BASELINE_ATTACHED" }
  ]
}
```

`status` values: `"passed"`, `"partial"`, `"blocked"`.

You can also target a specific environment:
```bash
curl -X POST http://localhost:8080/api/v1/projects/proj_myapp001/promotions/evaluate \
  -H "X-API-Key: <key>" \
  -H "Content-Type: application/json" \
  -d '{"target_environment": "prod"}'
```

---

## 4. Findings

Findings represent security or compliance issues discovered by scans, evaluators, or manual review.

**Ingest findings:**
```bash
curl -X POST http://localhost:8080/api/v1/findings/ingest \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  -H "Content-Type: application/json" \
  -d '{
    "findings": [
      {
        "finding_id": "find_001",
        "project_id": "proj_myapp001",
        "source": {
          "tool_name": "my-evaluator",
          "tool_type": "internal_eval"
        },
        "environment": "pilot",
        "category": "prompt_injection",
        "severity": "high",
        "title": "User input passed to system prompt without sanitization",
        "normalized": true
      }
    ],
    "source_batch": {
      "batch_id": "batch_001",
      "source_system": "my-evaluator",
      "trust_label": "trusted_internal"
    }
  }'
```

Response:
```json
{
  "schema_version": "1.1",
  "batch_id": "batch_001",
  "accepted_count": 1,
  "quarantined_count": 0,
  "normalized_count": 0,
  "timestamp": "2026-04-21T09:00:00Z"
}
```

**Finding shape — required fields:**

| Field | Type | Notes |
|-------|------|-------|
| `finding_id` | string | Your ID; prefix `find_` recommended |
| `project_id` | string | Must match an existing project |
| `source` | object | `tool_name` and `tool_type` at minimum |
| `environment` | string | `pilot`, `dev`, or `prod` |
| `category` | string | e.g. `prompt_injection`, `secret_leak`, `policy_violation` |
| `severity` | string | `critical`, `high`, `medium`, `low`, `info` |
| `title` | string | Short description |

**Optional fields:** `description`, `cvss_score`, `cwe_ids`, `compliance_refs`, `affected_components`, `verdict`.

`trust_label` on the batch controls how PeaRL weights the findings:
- `trusted_internal` — first-party scan, full weight
- `trusted_external_registered` — registered external adapter
- `untrusted_external` — external, reduced weight
- `manual_unverified` — human-entered, no automated weight

**List findings for a project:**
```bash
curl "http://localhost:8080/api/v1/projects/proj_myapp001/findings?status=open&severity=critical" \
  -H "X-API-Key: <key>"
```

---

## 5. Approvals

Approvals are how gates route decisions to humans. Agents create approval requests; human reviewers decide.

**Create an approval request (agent-initiated):**
```bash
curl -X POST http://localhost:8080/api/v1/approvals/requests \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  -H "Content-Type: application/json" \
  -d '{
    "approval_request_id": "appr_jkl345",
    "project_id": "proj_myapp001",
    "environment": "pilot",
    "request_type": "deployment_gate",
    "request_data": {
      "reason": "Deploying auth refactor — human review required before proceeding."
    }
  }'
```

`request_type` values: `deployment_gate`, `auth_flow_change`, `network_policy_change`, `exception`, `remediation_execution`, `promotion_gate`.

**Get an approval request:**
```bash
curl http://localhost:8080/api/v1/approvals/appr_jkl345 \
  -H "X-API-Key: <key>"
```

Response includes `status` (`pending`, `approved`, `rejected`, `needs_info`).

**Decide on an approval (reviewer role required):**
```bash
curl -X POST http://localhost:8080/api/v1/approvals/appr_jkl345/decide \
  -H "X-API-Key: <reviewer-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "approve",
    "decided_by": "alice@example.com",
    "reason": "Reviewed diff — change looks safe to proceed."
  }'
```

`decision` values: `"approve"` or `"reject"`. Agents that attempt this endpoint with a non-reviewer key receive `403 Forbidden` — this is correct behavior.

When a `promotion_gate` approval is approved, PeaRL automatically advances `current_environment` on the project and writes a promotion history record.

**List pending approvals:**
```bash
curl "http://localhost:8080/api/v1/approvals/pending?project_id=proj_myapp001" \
  -H "X-API-Key: <key>"
```

---

## 6. Workloads

Workloads track active agent instances. Register on startup, heartbeat periodically, deregister on exit.

**Register a workload:**
```bash
curl -X POST http://localhost:8080/api/v1/workloads/register \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  -H "Content-Type: application/json" \
  -d '{
    "svid": "worker-v1/session-abc",
    "task_packet_id": "tp_ghi012",
    "agent_id": "worker-v1"
  }'
```

The `svid` (service identity) must be unique. Use `agent_id/session_id` or similar.

Response:
```json
{
  "workload_id": "wkld_xyz",
  "svid": "worker-v1/session-abc",
  "status": "active",
  "registered_at": "2026-04-21T09:00:00Z"
}
```

**Deregister a workload (and materialize a factory run):**
```bash
curl -X DELETE "http://localhost:8080/api/v1/workloads/worker-v1%2Fsession-abc?frun_id=frun_abc123" \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"
```

The `frun_id` query parameter is required to materialize the factory run summary. It must match the `session_id` you used in cost entries (see section 7). URL-encode the SVID if it contains `/`.

Response:
```json
{
  "workload_id": "wkld_xyz",
  "status": "inactive"
}
```

Workloads with no heartbeat for more than 5 minutes are automatically marked inactive on the next read.

---

## 7. Cost Entries

Push LLM cost telemetry during agent execution. These entries are aggregated into factory run summaries when the workload is deregistered.

```bash
curl -X POST http://localhost:8080/api/v1/projects/proj_myapp001/governance-costs \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  -H "Content-Type: application/json" \
  -d '{
    "entries": [
      {
        "timestamp": "2026-04-21T09:05:00Z",
        "environment": "pilot",
        "workflow": "fix",
        "model": "claude-sonnet-4-6",
        "cost_usd": 0.0023,
        "duration_ms": 4200,
        "num_turns": 3,
        "tools_called": ["read_file", "edit_file", "bash"],
        "tool_count": 3,
        "success": true,
        "session_id": "frun_abc123"
      }
    ]
  }'
```

**Cost entry fields:**

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `timestamp` | ISO 8601 string | yes | When the call occurred |
| `environment` | string | yes | `pilot`, `dev`, or `prod` |
| `workflow` | string | yes | Task type / workflow label |
| `model` | string | yes | Model identifier |
| `cost_usd` | float | yes | Cost of this call |
| `session_id` | string | yes | Must match the `frun_id` used at deregister |
| `duration_ms` | int | no | |
| `num_turns` | int | no | Conversation turns |
| `tools_called` | string[] | no | Tool names used |
| `success` | bool | no | Defaults to `true` |

Response:
```json
{
  "received": 1,
  "created": 1
}
```

---

## 8. Factory Run Summaries

After deregistering a workload with a `frun_id`, retrieve the aggregated run summary:

```bash
curl http://localhost:8080/api/v1/workloads/run-summaries/frun_abc123 \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"
```

Response:
```json
{
  "frun_id": "frun_abc123",
  "project_id": "proj_myapp001",
  "task_packet_id": "tp_ghi012",
  "svid": "worker-v1/session-abc",
  "environment": "pilot",
  "outcome": "success",
  "total_cost_usd": 0.0023,
  "models_used": ["claude-sonnet-4-6"],
  "tools_called": ["read_file", "edit_file", "bash"],
  "duration_ms": 4200,
  "anomaly_flags": [],
  "promoted": false,
  "promotion_env": null,
  "started_at": "2026-04-21T09:00:00Z",
  "completed_at": "2026-04-21T09:05:00Z"
}
```

`anomaly_flags` is populated automatically if PeaRL detects anomalous patterns (rapid promotion, missing receipts, bulk false-positive marking, etc.). A non-empty list is a signal that the run requires human review before promotion.

---

## 9. Health

**Liveness probe** — always 200 if the process is up:
```bash
curl http://localhost:8080/health/live
```
```json
{"status": "alive"}
```

**Readiness probe** — checks DB and Redis:
```bash
curl http://localhost:8080/health/ready
```
```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "redis": "ok"
  }
}
```

Returns `503` with `status: "not_ready"` if either dependency is unavailable. In local dev mode (`PEARL_LOCAL=1`), Redis is not required and returns `"disabled"` rather than an error.
