# Agent Team Workflows

Practical playbook for agents and agent teams operating under PeaRL governance. Each workflow shows the sequence of MCP tool calls (available via LiteLLM as `PeaRL-pearl_*`) and REST calls needed to accomplish the goal.

---

## Workflow 1: Onboarding a New Agent Team

Run this the first time a team attaches to PeaRL, before any factory cycle or gate evaluation.

### Step 1 — Bootstrap the project

```
pearl_register_project({
  name: "my-agent-team",
  owner_team: "ape-team",
  business_criticality: "moderate",
  external_exposure: "internal_only",
  ai_enabled: true,
  description: "Coordinator + worker team for automated code review"
})
```

Response includes a generated `project_id` (e.g. `proj_my-agent-team`), a `.pearl.yaml` template, and a compiled context package. Write those files to disk as instructed.

### Step 2 — Check what org baseline applies

```
pearl_get_recommended_baseline({
  ai_enabled: true,
  business_criticality: "moderate"
})
```

Returns three tiered baselines (Essential / AI-Standard / AI-Comprehensive) and a recommendation. Apply the recommended tier:

```
pearl_apply_recommended_baseline({
  project_id: "proj_my-agent-team"
})
```

### Step 3 — Register the coordinator for pilot

```
pearl_register_agent_for_stage({
  project_id: "proj_my-agent-team",
  environment: "pilot",
  agent_id: "coordinator-v1",
  role: "coordinator",
  autonomy_mode: "supervised"
})
```

### Step 4 — Register worker agents

Repeat for each worker:

```
pearl_register_agent_for_stage({
  project_id: "proj_my-agent-team",
  environment: "pilot",
  agent_id: "worker-code-review-v1",
  role: "worker"
})
```

### Step 5 — Set the environment profile for pilot

```
pearl_set_env_profile({
  project_id: "proj_my-agent-team",
  profile: {
    schema_version: "1.1",
    profile_id: "envp_pilot-001",
    environment: "pilot",
    delivery_stage: "pilot",
    risk_level: "moderate",
    autonomy_mode: "supervised_autonomous",
    approval_level: "standard",
    allowed_capabilities: ["code_read", "code_write", "test_run"],
    blocked_capabilities: ["deploy", "secret_read"]
  }
})
```

### Step 6 — Check initial gate readiness

```
pearl_evaluate_promotion({
  project_id: "proj_my-agent-team"
})
```

Expected response at first run — all gates are blocked because no scan has been completed and no evidence has been submitted:

```json
{
  "status": "blocked",
  "source_environment": "pilot",
  "target_environment": "dev",
  "passed": 0,
  "total": 8,
  "blockers": [
    {
      "rule_type": "AI_SCAN_COMPLETED",
      "message": "No AI security scan on record for pilot.",
      "fix_guidance": "Call pearl_run_scan or pearl_trigger_mass_scan to complete a scan."
    },
    {
      "rule_type": "CLAUDE_MD_GOVERNANCE_PRESENT",
      "message": "Governance block not confirmed in CLAUDE.md.",
      "fix_guidance": "Write the PeaRL governance block to CLAUDE.md, then call pearl_confirm_claude_md."
    }
  ]
}
```

Work through the blockers in subsequent workflows.

---

## Workflow 2: Running a Factory Cycle (Single Agent Run)

One factory cycle = one unit of purposeful agent work (a task, a repair, a scan). This is the inner loop that every worker runs.

### Step 1 — Register the workload (agent goes active)

REST call — no MCP tool for this step:

```bash
POST /api/v1/workloads/register
Content-Type: application/json
X-API-Key: <key>

{
  "svid": "worker-code-review-v1/run-2026-04-21T09:00:00",
  "task_packet_id": "",
  "agent_id": "worker-code-review-v1"
}
```

Response:

```json
{
  "workload_id": "wkld_abc123",
  "svid": "worker-code-review-v1/run-2026-04-21T09:00:00",
  "status": "active",
  "registered_at": "2026-04-21T09:00:00Z"
}
```

### Step 2 — Generate a task packet

```
pearl_generate_task_packet({
  project_id: "proj_my-agent-team",
  task_type: "fix",
  task_summary: "Resolve SQL injection finding in user-search endpoint",
  environment: "pilot"
})
```

Response includes `packet_id`, the relevant governance controls for this task type, and an initial `execution_phase` of `"planning"`.

### Step 3 — Claim the task packet

```
pearl_claim_task_packet({
  packet_id: "tp_xyz789",
  agent_id: "worker-code-review-v1"
})
```

Status transitions to `in_progress`. The task is now exclusively assigned to this agent.

### Step 4 — Agent executes

During execution the agent calls the appropriate tools (code edit, test run, etc.). Push cost telemetry as work progresses:

```bash
POST /api/v1/projects/proj_my-agent-team/governance-costs
Content-Type: application/json
X-API-Key: <key>

{
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
      "success": true,
      "session_id": "frun_abc123"
    }
  ]
}
```

The `session_id` field becomes the `frun_id` that ties this cost ledger entry to the factory run summary.

### Step 5 — Complete the task packet

```
pearl_complete_task_packet({
  packet_id: "tp_xyz789",
  status: "success",
  changes_summary: "Parameterized the user-search query to eliminate injection vector",
  finding_ids_resolved: ["find_def456"]
})
```

### Step 6 — Deregister the workload (materializes the factory run)

```bash
DELETE /api/v1/workloads/worker-code-review-v1%2Frun-2026-04-21T09:00:00?frun_id=frun_abc123
X-API-Key: <key>
```

The `frun_id` query parameter triggers the factory run materializer, which aggregates all cost entries for this session into a single summary record.

### Step 7 — Retrieve the run summary

```
pearl_get_run_summary({
  frun_id: "frun_abc123",
  project_id: "proj_my-agent-team"
})
```

Response:

```json
{
  "frun_id": "frun_abc123",
  "project_id": "proj_my-agent-team",
  "task_packet_id": "tp_xyz789",
  "environment": "pilot",
  "outcome": "success",
  "total_cost_usd": 0.0023,
  "models_used": ["claude-sonnet-4-6"],
  "tools_called": ["read_file", "edit_file", "bash"],
  "duration_ms": 4200,
  "anomaly_flags": [],
  "promoted": false
}
```

---

## Workflow 3: Promoting from Pilot to Dev

Promotion requires all gate rules to pass (or be explicitly waived by a human), followed by human sign-off.

### Step 1 — Evaluate the gate

```
pearl_evaluate_promotion({
  project_id: "proj_my-agent-team",
  target_environment: "dev"
})
```

### Step 2 — Read the blockers

Each blocker in the response has three fields:

- `rule_type` — the gate rule name
- `message` — what is missing or failing
- `fix_guidance` — concrete action to take

Example blocker:

```json
{
  "rule_type": "AI_SCAN_COMPLETED",
  "message": "No AI security scan on record for pilot.",
  "fix_guidance": "Call pearl_run_scan or pearl_trigger_mass_scan to complete a scan."
}
```

### Step 3 — Resolve each blocker

Common resolutions:

**AI scan not completed:**
```
pearl_run_scan({
  project_id: "proj_my-agent-team",
  target_path: "/workspace/my-agent-team",
  environment: "pilot"
})
```
Poll `pearl_get_job_status({ job_id: "<returned job_id>" })` until `status: "completed"`.

**CLAUDE.md governance block not confirmed:**
Write the PeaRL governance block to `CLAUDE.md`, then:
```
pearl_confirm_claude_md({
  project_id: "proj_my-agent-team"
})
```

**Framework control not evidenced (AIUC-1, OWASP LLM, etc.):**
```
pearl_submit_evidence({
  project_id: "proj_my-agent-team",
  environment: "pilot",
  evidence_type: "attestation",
  evidence_data: {
    control_id: "aiuc1/security/b001_2_security_program_integration",
    findings: "Rate limiting implemented via slowapi in middleware/rate_limit.py",
    artifact_refs: ["src/pearl/api/middleware/rate_limit.py"],
    attested_by: "coordinator-v1"
  }
})
```

### Step 4 — Re-evaluate until passing

Repeat `pearl_evaluate_promotion` after each resolution. When all blockers are cleared:

```json
{
  "status": "passed",
  "passed": 8,
  "total": 8,
  "blockers": []
}
```

### Step 5 — Request promotion

```
pearl_request_promotion({
  project_id: "proj_my-agent-team",
  target_environment: "dev"
})
```

Returns an `approval_request_id`. A promotion gate approval is created in PeaRL and notifications go to configured org-level sinks (Slack, webhook, etc.).

**Stop here.** Do not attempt to approve the promotion yourself. The agent must wait for a human reviewer.

### Step 6 — Check approval status

```
pearl_check_approval_status({
  approval_request_id: "appr_jkl345"
})
```

Or poll the REST endpoint:

```bash
GET /api/v1/approvals/appr_jkl345
```

### Step 7 — On approval

When a human approves via the dashboard (`POST /api/v1/approvals/appr_jkl345/decide`), the project's `current_environment` advances to `dev` automatically. The agent can then proceed to operate in the dev environment.

---

## Workflow 4: Handling a Gate Block

When a gate evaluation returns `status: "blocked"`, the agent must not attempt to route around it.

### Step 1 — Read the blocker details

```json
{
  "status": "blocked",
  "blockers": [
    {
      "rule_type": "NO_CRITICAL_FINDINGS",
      "message": "2 open critical findings must be resolved before promotion.",
      "fix_guidance": "Resolve or obtain an approved exception for all critical findings."
    }
  ]
}
```

### Step 2 — Determine whether the block requires human decision

Some blockers can be resolved by the agent (running a scan, submitting evidence). Others require human decision:

- A gate requires risk acceptance → `pearl_request_approval`
- A critical finding cannot be automatically fixed → `pearl_create_exception`
- A deployment gate requires reviewer sign-off → `pearl_request_approval`

### Step 3 — Request approval

```
pearl_request_approval({
  approval_request_id: "appr_new001",
  project_id: "proj_my-agent-team",
  request_type: "deployment_gate",
  environment: "pilot",
  request_data: {
    reason: "Critical finding find_def456 (SQL injection) requires human risk acceptance before deployment can proceed.",
    rule_type: "NO_CRITICAL_FINDINGS",
    finding_ids: ["find_def456"]
  }
})
```

### Step 4 — Stop and inform the user

Surface the `approval_request_id` to the user. Example message:

> Gate blocked: 2 critical findings must be resolved or accepted before promotion to dev. I have submitted approval request `appr_new001` for human review. Please visit the PeaRL dashboard to decide. I will not proceed until a decision is recorded.

Do not attempt any further promotion steps. Do not call `pearl_decide_approval` — that requires reviewer role and agents receive 403.

### Step 5 — On human resolution

After the human decides (via `POST /api/v1/approvals/{id}/decide`), poll:

```
pearl_check_approval_status({
  approval_request_id: "appr_new001"
})
```

- `status: "approved"` → re-evaluate the gate and proceed if it now passes
- `status: "rejected"` → surface the rejection reason to the user and stop

---

## Workflow 5: Multi-Agent Team Coordination

One project can have a coordinator, multiple workers, and one or more evaluators. Each runs independent factory cycles.

### Coordinator responsibilities

1. Register the project (`pearl_register_project`)
2. Apply baseline (`pearl_apply_recommended_baseline`)
3. Register each team member for the target environment (`pearl_register_agent_for_stage`)
4. After all workers finish their cycles, aggregate results:

```
pearl_get_run_summary({ frun_id: "frun_worker1_session" })
pearl_get_run_summary({ frun_id: "frun_worker2_session" })
```

5. Request promotion only when all worker runs returned `outcome: "success"` and no `anomaly_flags`

### Worker responsibilities

Each worker runs an independent factory cycle (Workflow 2). Workers do not call `pearl_request_promotion` — that is the coordinator's responsibility.

### Evaluator responsibilities

Evaluators run compliance checks and submit findings:

```
pearl_ingest_findings({
  findings: [
    {
      finding_id: "find_eval001",
      project_id: "proj_my-agent-team",
      source: { tool_name: "evaluator-v1", tool_type: "internal_eval" },
      environment: "pilot",
      category: "policy_violation",
      severity: "medium",
      title: "Worker agent used blocked capability: deploy",
      normalized: true
    }
  ],
  source_batch: {
    batch_id: "batch_eval001",
    source_system: "evaluator-v1",
    trust_label: "trusted_internal"
  }
})
```

### Promotion gate

The coordinator requests promotion only after:
- All worker run summaries show `outcome: "success"`
- All evaluator findings are resolved or accepted
- `pearl_evaluate_promotion` returns `status: "passed"`

---

## Workflow 6: Requesting Human Approval for a Sensitive Action

Any irreversible or policy-gated action — deployment, exception, network policy change — requires explicit human approval before proceeding.

### Step 1 — Determine the request type

| Situation | `request_type` |
|-----------|---------------|
| Deploying to a new environment | `deployment_gate` |
| Requesting a policy exception | `exception` |
| Promotion gate sign-off | `promotion_gate` |
| Auth flow change | `auth_flow_change` |
| Network policy change | `network_policy_change` |
| Remediation execution in prod | `remediation_execution` |

### Step 2 — Submit the approval request

```
pearl_request_approval({
  approval_request_id: "appr_sens001",
  project_id: "proj_my-agent-team",
  request_type: "deployment_gate",
  environment: "dev",
  request_data: {
    reason: "Requesting approval to deploy refactored auth module to dev. Change includes a new JWT validation path — human review required before deployment.",
    commit_sha: "a1b2c3d4",
    pr_url: "https://github.com/org/repo/pull/42"
  }
})
```

Response:

```json
{
  "approval_request_id": "appr_sens001",
  "status": "pending",
  "dashboard_url": "http://localhost:5177/approvals/appr_sens001"
}
```

### Step 3 — Return the approval ID to the user and stop

Return the `approval_request_id` and dashboard URL. Do not proceed with the deployment. Do not take any further action until the human decides.

### Step 4 — Poll for the decision (optional)

```
pearl_check_approval_status({
  approval_request_id: "appr_sens001"
})
```

Wait for `status` to leave `"pending"` before acting.

### Step 5 — Act on the decision

- `"approved"` → proceed with the gated action
- `"rejected"` → surface `reason` from the decision to the user and stop; do not attempt an alternate path
