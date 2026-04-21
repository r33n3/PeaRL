# LiteLLM MCP Adapter Integration

PeaRL exposes 55 governance tools via the Model Context Protocol (MCP). Agent teams do not call PeaRL's REST API directly. Instead, LiteLLM acts as the enforcement and audit layer between agent code and PeaRL — centralizing auth, spend controls, and access scoping so that individual agent teams never hold raw PeaRL credentials.

---

## Why This Model

- **Single credential boundary.** Agent teams hold LiteLLM virtual keys, not PeaRL API keys. Revoking a virtual key immediately kills all PeaRL tool access for that team without touching PeaRL's own key store.
- **Spend and rate-limit enforcement.** LiteLLM enforces per-team token budgets before requests reach PeaRL.
- **Audit trail.** LiteLLM logs every tool invocation (team, timestamp, arguments) independently of PeaRL's own audit log, giving a second attestation point.
- **Tool discovery.** Agents enumerate tools through LiteLLM's `/mcp/tools/list` endpoint — PeaRL's internal endpoint is not exposed to the agent network.

---

## Architecture

```
Agent code
    |
    | POST /mcp/tools/call  (LiteLLM virtual key)
    v
LiteLLM proxy  (localhost:4000)
    |  .mcp.json resolves "PeaRL" server
    |  X-API-Key forwarded to PeaRL
    v
PeaRL MCP endpoint  (http://pearl-api:8080/api/v1/mcp)
    |  HTTP + SSE transport
    v
PeaRL API  (FastAPI)
    |
    v
PostgreSQL
```

LiteLLM reads `.mcp.json` from the working directory and registers PeaRL as a named MCP server. Agents never need to know the PeaRL endpoint URL.

---

## Setup

### 1. LiteLLM `.mcp.json`

Place this file in the LiteLLM working directory. LiteLLM auto-resolves it on startup.

```json
{
  "mcpServers": {
    "PeaRL": {
      "url": "http://pearl-api:8080/api/v1/mcp",
      "transport": "http"
    }
  }
}
```

LiteLLM will pass the agent team's virtual key to PeaRL as `X-API-Key` on every forwarded request. No additional auth wiring is required in agent code.

### 2. Provision a PeaRL API Key for LiteLLM

LiteLLM needs a PeaRL service account key with sufficient scope to forward requests on behalf of agent teams. Create it via the PeaRL API (admin credentials required):

```bash
curl -X POST http://pearl-api:8080/api/v1/api-keys \
  -H "Authorization: Bearer <admin-token>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "litellm-proxy",
    "roles": ["service_account"],
    "scopes": ["mcp:*"]
  }'
```

Set the returned key as `PEARL_API_KEY` in LiteLLM's environment.

### 3. Provision LiteLLM Virtual Keys for Agent Teams

Each agent team gets a LiteLLM virtual key. Scope restrictions here are enforced before the request reaches PeaRL.

```bash
# Example: provision a key for the WTK agent team
litellm --create-virtual-key \
  --alias "wtk-agents" \
  --max-budget 10.00 \
  --allowed-mcp-tools "PeaRL-pearl_evaluate_promotion,PeaRL-pearl_register_agent_for_stage,PeaRL-pearl_list_gates,PeaRL-pearl_get_task_packet,PeaRL-pearl_request_approval"
```

Agents use the virtual key as a Bearer token against LiteLLM — they never see the underlying PeaRL key.

---

## Tool Naming Convention

PeaRL tool names follow the pattern:

```
{mcpServerName}-{toolName}
```

| PeaRL internal name | LiteLLM tool name |
|---|---|
| `pearl_evaluate_promotion` | `PeaRL-pearl_evaluate_promotion` |
| `pearl_register_agent_for_stage` | `PeaRL-pearl_register_agent_for_stage` |
| `pearl_list_gates` | `PeaRL-pearl_list_gates` |
| `pearl_request_approval` | `PeaRL-pearl_request_approval` |
| `pearl_submit_frun_report` | `PeaRL-pearl_submit_frun_report` |

The MCP server name (`PeaRL`) matches the key in `.mcp.json`. All 55 tools follow this `PeaRL-pearl_*` pattern.

### Discovering Available Tools

```bash
curl -X POST http://localhost:4000/mcp/tools/list \
  -H "Authorization: Bearer <virtual-key>"
```

Response excerpt:

```json
{
  "tools": [
    {
      "name": "PeaRL-pearl_evaluate_promotion",
      "description": "Evaluate whether a project is cleared for promotion to the next stage.",
      "inputSchema": { ... }
    },
    ...
  ]
}
```

Do not hard-code tool lists in agent logic. Use `tools/list` to enumerate and cache per session.

---

## Key Integration Patterns

### Stage-Agnostic Promotion Evaluation

PeaRL owns the pipeline definition. Agents must not maintain a local list of stage names or assume what the next stage is.

**Call:**

```json
{
  "name": "PeaRL-pearl_evaluate_promotion",
  "arguments": {
    "project_id": "proj_wtk"
  }
}
```

**Response:**

```json
{
  "project_id": "proj_wtk",
  "source_environment": "pilot",
  "target_environment": "dev",
  "status": "blocked",
  "blockers": [
    {
      "gate_id": "gate_abc123",
      "gate_name": "Security Scan Required",
      "reason": "No passing MASS scan found for this commit"
    }
  ]
}
```

The agent reads `source_environment` and `target_environment` from the response. It does not infer, cache, or hardcode these values.

Only pass `target_environment` explicitly when targeting a non-sequential transition — for example, rolling back from `prod` to `preprod`. For normal forward promotion, omit it.

### Agent Registration Flow

Before participating in a factory run, an agent registers itself for the relevant stage. This requires the virtual key to have `operator` or `service_account` role in PeaRL.

**Call:**

```json
{
  "name": "PeaRL-pearl_register_agent_for_stage",
  "arguments": {
    "project_id": "proj_wtk",
    "agent_id": "agent_wtk_builder_01",
    "stage": "pilot",
    "capabilities": ["build", "test", "lint"]
  }
}
```

**Response:**

```json
{
  "registration_id": "reg_xyz789",
  "agent_id": "agent_wtk_builder_01",
  "project_id": "proj_wtk",
  "stage": "pilot",
  "status": "active",
  "registered_at": "2026-04-21T10:00:00Z"
}
```

### Gate Evaluation and Reading Blockers

List all gates for a project to understand what conditions must pass before promotion:

**Call:**

```json
{
  "name": "PeaRL-pearl_list_gates",
  "arguments": {
    "project_id": "proj_wtk"
  }
}
```

**Response:**

```json
{
  "gates": [
    {
      "gate_id": "gate_abc123",
      "name": "Security Scan Required",
      "environment": "pilot",
      "auto_pass": false,
      "status": "pending"
    },
    {
      "gate_id": "gate_def456",
      "name": "Test Coverage Threshold",
      "environment": "pilot",
      "auto_pass": true,
      "status": "passed"
    }
  ]
}
```

When `pearl_evaluate_promotion` returns `"status": "blocked"`, the `blockers` array identifies which gates are failing. Agents surface these to the human operator — they do not attempt to self-approve or route around them.

To request human approval for a blocked gate:

**Call:**

```json
{
  "name": "PeaRL-pearl_request_approval",
  "arguments": {
    "project_id": "proj_wtk",
    "request_type": "deployment_gate",
    "environment": "pilot",
    "request_data": {
      "gate_id": "gate_abc123",
      "reason": "Requesting manual override: MASS scan is in progress and expected to complete within 10 minutes"
    }
  }
}
```

After calling `pearl_request_approval`, the agent stops and waits for a human decision. It does not poll or retry the gate unilaterally.

### Factory Run Reporting

Submit a factory run report at the end of a session to record outcomes, findings, and session metadata. The `frun_id` ties the report to a specific factory run; `session_id` is the agent's local session identifier.

**Call:**

```json
{
  "name": "PeaRL-pearl_submit_frun_report",
  "arguments": {
    "project_id": "proj_wtk",
    "frun_id": "frun_2026042101",
    "session_id": "sess_wtk_builder_01_abc",
    "stage": "pilot",
    "outcome": "success",
    "findings": [],
    "metadata": {
      "duration_seconds": 142,
      "tasks_completed": 7
    }
  }
}
```

**Response:**

```json
{
  "report_id": "rpt_pqr901",
  "project_id": "proj_wtk",
  "frun_id": "frun_2026042101",
  "status": "accepted",
  "created_at": "2026-04-21T10:02:22Z"
}
```

---

## Auth and Access Control

### Virtual Key Scopes as a Kill Switch

Every LiteLLM virtual key maps to a set of allowed PeaRL tools. Revoking the key immediately blocks all PeaRL access for that agent team — no changes required on the PeaRL side.

```bash
# Revoke a team's access
litellm --delete-virtual-key --alias "wtk-agents"
```

All subsequent tool calls from that team return `401 Unauthorized` from LiteLLM before reaching PeaRL.

### Role Requirements

| Tool category | Required PeaRL role |
|---|---|
| Read (list gates, get task packets, evaluate promotion) | `viewer` |
| Write (submit reports, register agents, request approval) | `operator` or `service_account` |
| Approve/decide gates | `admin` (human-only — agents will receive 403) |
| Create exceptions | `admin` (human-only — agents will receive 403) |

The LiteLLM virtual key inherits the role of the PeaRL service account key it uses. Scope the service account key to `operator` for most agent teams.

### Header Flow

```
Agent → LiteLLM (Authorization: Bearer <virtual-key>)
             ↓
         LiteLLM → PeaRL (X-API-Key: <pearl-service-account-key>)
```

PeaRL sees only the service account key. Individual agent team identities are tracked in LiteLLM's audit log via the virtual key alias.

---

## Error Handling

### Stub Fallback Pattern

When PeaRL is temporarily unreachable (during startup, network partition, or deploy), agents should apply a stub fallback for non-critical read operations and propagate errors for write operations.

```typescript
async function evaluatePromotion(projectId: string) {
  try {
    return await callMcpTool('PeaRL-pearl_evaluate_promotion', {
      project_id: projectId
    })
  } catch (e) {
    if (
      e.message.includes('unreachable') ||
      e.message.includes('tool not found') ||
      e.message.includes('connection refused')
    ) {
      // PeaRL is down — treat as unknown, do not assume clearance
      return { status: 'unknown', blockers: [], source_environment: null, target_environment: null }
    }
    // Auth errors, validation errors, and gate blocks are real — propagate
    throw e
  }
}
```

### Which Errors to Propagate vs Absorb

| Error condition | Action |
|---|---|
| `401 Unauthorized` | Propagate — virtual key revoked or expired |
| `403 Forbidden` | Propagate — agent attempted a human-only action (correct behavior) |
| `404 Not Found` | Propagate — project or resource does not exist |
| `422 Unprocessable Entity` | Propagate — malformed arguments |
| `503 Service Unavailable` | Absorb with stub if read-only; propagate if write |
| Network timeout / connection refused | Absorb with stub if read-only; propagate if write |
| `tool not found` | Absorb — PeaRL may be restarting; retry after backoff |

Never absorb a `403` and attempt to find an alternate path. A 403 on an approve or decide endpoint means the action requires a human — that is the correct behavior, not an error to route around.

---

## Common Pitfalls

### Do Not Cache the Stage List Locally

PeaRL is the authoritative source for pipeline stage definitions. Do not store stage names (`pilot`, `dev`, `preprod`, `prod`) in agent config or code. If PeaRL's pipeline changes, agents that cache stage names will send invalid `target_environment` values and receive `422` errors.

Read `source_environment` and `target_environment` from `pearl_evaluate_promotion` responses only.

### Do Not Send `target_environment` for Normal Forward Promotion

`target_environment` is optional. When omitted, PeaRL resolves the next stage automatically from the project's current position in the pipeline. Only supply it for explicit non-sequential transitions (e.g., rollbacks or hotfix paths).

Sending the wrong `target_environment` — such as a cached value that no longer matches the pipeline — will cause the call to fail with a `422` or return incorrect gate evaluation results.

### LiteLLM Tool Cache — Restart to Pick Up New Tools

LiteLLM caches the tool list from PeaRL at session startup. If PeaRL is updated and new tools are added, existing LiteLLM sessions will not see them. Restart the LiteLLM proxy after a PeaRL upgrade to refresh the tool manifest.

Agents that call a tool name that LiteLLM does not have in its cache will receive a `tool not found` error. This should trigger the stub fallback (see above), not a hard failure.

### 403 on Approve/Decide Endpoints Is Correct

Agents will receive `403 Forbidden` when calling `pearl_decide_approval`, `pearl_create_exception`, or any other human-review endpoint — regardless of their virtual key scopes. These endpoints require `admin` role and are intentionally inaccessible to service accounts.

The correct response sequence when a gate blocks an agent:

1. Call `pearl_request_approval` with the blocked action and reason.
2. Inform the human operator what was blocked and why.
3. Stop — do not poll, retry, or attempt alternate paths.

A 403 is governance working as designed.
