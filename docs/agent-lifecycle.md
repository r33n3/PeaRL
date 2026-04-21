# Agent Team Lifecycle in PeaRL

This document describes the full lifecycle of an agent team operating under PeaRL governance — from initial project registration through task execution, gate evaluation, and environment promotion. All API interactions are via the PeaRL REST API at `/api/v1` or via MCP tools accessible through the LiteLLM proxy (tool names prefixed `PeaRL-pearl_*`).

---

## Typical Sequence (end-to-end)

1. Register the project — `pearl_register_project` or `POST /projects/register`
2. Register agents for the target stage — `pearl_register_agent_for_stage` (coordinator, then workers and evaluators)
3. Attach org baseline and app spec — `pearl_set_org_baseline`, `pearl_set_app_spec`, `pearl_set_env_profile`
4. Compile the governance context — `pearl_compile_context` → poll `pearl_get_job_status`
5. Register the active workload (agent goes live) — `POST /workloads/register`
6. Create and claim a task packet — `pearl_generate_task_packet` → `pearl_claim_task_packet`
7. Execute work, send periodic heartbeats — `POST /workloads/{svid}/heartbeat`
8. Complete the task packet — `pearl_complete_task_packet`
9. Evaluate gate readiness and request promotion — `pearl_evaluate_promotion` → `pearl_request_promotion`
10. Deregister the workload and materialize the run summary — `DELETE /workloads/{svid}?frun_id={session_id}`

---

## 1. Project Registration

A project is the top-level governance unit in PeaRL. One project covers the entire agent team: coordinator, workers, and evaluators are all members of the same project.

**MCP tool:** `pearl_register_project`
**REST endpoint:** `POST /api/v1/projects/register`

The `pearl_register_project` tool is the preferred one-shot bootstrap path. It creates the project, builds a minimal app spec, compiles the governance context, and returns ready-to-write config file content (`.pearl.yaml`, `.pearl/pearl-dev.toml`, `.pearl/compiled-context-package.json`). After writing those files, all other MCP tools work immediately with no further setup.

Key request fields:
- `name` — human-readable project name; used to derive the `proj_` ID slug
- `owner_team` — team responsible for this project
- `business_criticality` — `low | moderate | high | mission_critical`; governs which gate tier applies
- `external_exposure` — `internal_only | partner | customer_facing | public`
- `ai_enabled` — set `true` for AI-native agent projects
- `description` (optional)
- `bu_id` (optional) — business unit scope

On success, PeaRL returns a `project_id` (e.g., `proj_my-agent-team`) and the derived config files.

If using the lower-level `pearl_create_project` tool, you supply a `project_id` directly (must match pattern `proj_[A-Za-z0-9_-]+`) along with the same classification fields.

---

## 2. Agent Registration

Once a project exists, each agent instance registers its identity and role for the environment it will operate in.

**MCP tool:** `pearl_register_agent_for_stage`
**REST endpoint:** `POST /api/v1/projects/{project_id}/register-agent-stage`

Request fields:
- `project_id` — the project this agent belongs to
- `environment` — the stage this agent operates in (`pilot`, `dev`, `prod`, etc.)
- `agent_id` — unique identifier for this agent instance (e.g., `saga-coordinator-v2`)
- `role` — `coordinator | worker | evaluator`
- `autonomy_mode` (optional) — `assistive | supervised | autonomous`; sets the `EnvironmentProfileRow.autonomy_mode` for this environment if provided

Coordinator registration replaces any existing coordinator record. Worker and evaluator registrations append to the `agent_members` JSON field (deduped by `agent_id`). Registering agents before any gate evaluation or task execution is important — it binds team identity to the project so gate evaluations can attribute actions to the correct team.

If `autonomy_mode` is provided, PeaRL updates the `EnvironmentProfileRow` for this project + environment combination, which influences what the gate evaluator requires before allowing promotion.

---

## 3. Baseline and Gate Attachment

PeaRL enforces governance through layered configuration: an org baseline, an app spec, and an environment profile. These must be attached before context compilation and gate evaluation can produce meaningful results.

**Org baseline** — `pearl_set_org_baseline` → `PUT /api/v1/projects/{project_id}/org-baseline`

The org baseline (stored as `OrgBaselineRow`) defines the minimum security controls for the organization: coding standards, IAM policies, network rules, logging requirements, and responsible AI requirements. It also supports per-environment escalation through `environment_defaults`. The baseline ID must match the pattern `orgb_[A-Za-z0-9_-]+`.

Use `pearl_get_org_baseline` to inspect the currently attached baseline before modifying it.

Use `pearl_get_recommended_baseline` to get tiered baseline options (Essential, AI-Standard, AI-Comprehensive) matched to your project's `ai_enabled` and `business_criticality` settings. `pearl_apply_recommended_baseline` applies the correct tier automatically.

**App spec** — `pearl_set_app_spec` → `PUT /api/v1/projects/{project_id}/app-spec`

The app spec defines components, trust boundaries, data classifications, responsible AI settings, and autonomous coding policies.

**Environment profile** — `pearl_set_env_profile` → `PUT /api/v1/projects/{project_id}/env-profile`

Sets the per-environment configuration: delivery stage, risk level, autonomy mode, allowed/blocked capabilities, and approval level. Approval level controls how stringent the human sign-off requirement is (`minimal | standard | elevated | high | strict`).

After all three are attached, they are compiled into a canonical governance context package via `pearl_compile_context`.

---

## 4. Context Compilation

**MCP tool:** `pearl_compile_context`
**REST endpoint:** `POST /api/v1/projects/{project_id}/compile`

Compilation merges the org baseline, app spec, and environment profile into a versioned, immutable context package. The result is stored as a `CompiledPackageRow` and returned in the response.

This call is asynchronous — it returns a `job_id`. Poll `pearl_get_job_status` until `status == "completed"` before generating task packets. Retrieve the compiled package with `pearl_get_compiled_package`.

The compiled package is required for task packet generation. If the baseline or app spec changes, recompile before the next agent run.

---

## 5. Workload Registration (Agent Goes Active)

When an agent instance starts executing, it registers itself as an active workload.

**REST endpoint:** `POST /api/v1/workloads/register`

Request fields:
- `svid` — service identity string (unique per agent instance, e.g., `spiffe://trust-domain/coordinator`)
- `task_packet_id` — the task packet this workload will execute (can be set after creation)
- `agent_id` — agent identifier
- `allowance_profile_id` (optional) — links to an `AllowanceProfileRow` for Layer 1–3 allowance enforcement
- `metadata` (optional) — arbitrary key-value data

PeaRL returns a `workload_id` and records the workload as `status: active`. The workload now appears in the registry and represents this agent in PeaRL's view.

**Heartbeats** — agents should send periodic heartbeats to maintain active status:
`POST /api/v1/workloads/{svid}/heartbeat`

Workloads with no heartbeat for more than 5 minutes are auto-marked inactive when the registry is read. Send heartbeats at least every 60–90 seconds during long-running tasks.

---

## 6. Task Packet Lifecycle

Task packets are the unit of work in PeaRL. Each packet scopes the governance context to a specific task type and records the execution phase as the agent progresses.

### 6a. Creation

**MCP tool:** `pearl_generate_task_packet`
**REST endpoint:** `POST /api/v1/projects/{project_id}/task-packets`

Request fields:
- `project_id`
- `task_type` — `feature | fix | remediation | refactor | config | policy`
- `task_summary` — short human-readable description (max 512 chars)
- `environment` — the environment the agent is operating in

The packet is created with `execution_phase = "planning"` and an empty `phase_history`. The packet ID uses the `tp_` prefix.

To include run tracking, embed `run_id` or `session_id` in `packet_data` at creation time. PeaRL uses this field to materialize a factory run summary when the packet completes.

### 6b. Claiming

**MCP tool:** `pearl_claim_task_packet`
**REST endpoint:** `POST /api/v1/task-packets/{packet_id}/claim`

Body: `{ "agent_id": "..." }`

Claiming sets packet status to `in_progress` and records which agent holds it. Only one agent should hold a packet at a time.

### 6c. Phase Transitions

Agents advance through execution phases using:
`PATCH /api/v1/task-packets/{packet_id}/phase`

Body: `{ "phase": "...", "agent_id": "..." }`

Legal forward transitions:
- `planning` → `coding` or `failed`
- `coding` → `testing` or `failed`
- `testing` → `review` or `failed`
- `review` → `complete` or `failed`

`complete` and `failed` are terminal. Attempting to transition from a terminal state returns a validation error.

### 6d. Completion

**MCP tool:** `pearl_complete_task_packet`
**REST endpoint:** `POST /api/v1/task-packets/{packet_id}/complete`

Request fields:
- `status` — `success | failed | partial`
- `changes_summary` — human-readable summary of changes made
- `finding_ids_resolved` — list of `find_` IDs resolved by this work
- `commit_ref`, `files_changed`, `evidence_notes` (optional audit fields)

On completion, PeaRL sets `execution_phase = "complete"` and records the outcome. If `packet_data["run_id"]` is set, factory run materialization is triggered as a fallback (the primary path is workload deregistration with `frun_id`).

---

## 7. Gate Evaluation and Promotion

PeaRL enforces a promotion pipeline: `pilot → dev → preprod → prod`. Gate evaluation is deterministic — no model calls. All rules are checked against the compiled context, findings, fairness evidence, and scan results.

### 7a. Evaluate Readiness

**MCP tool:** `pearl_evaluate_promotion`
**REST endpoint:** `POST /api/v1/projects/{project_id}/promotions/evaluate`

If `target_environment` is omitted, PeaRL resolves the next environment in the pipeline automatically from the current `EnvironmentProfileRow`. The response includes:
- `evaluation_id`
- `source_environment` and `target_environment`
- `status` — `passed | failed`
- `rule_results` — per-rule pass/fail with details
- `blockers` — rules that are failing and what they require

Common gate rules that can block promotion:
- `AI_SCAN_COMPLETED` — a security scan must have run
- `AI_RISK_ACCEPTABLE` — MASS scan risk score must be below threshold (default 7.0)
- `CRITICAL_FINDINGS_ZERO` — no open critical-severity findings
- `NO_PROMPT_INJECTION` — no open prompt injection findings
- `FAIRNESS_ATTESTATION_SIGNED` — a fairness evidence package must be signed
- `CLAUDE_MD_GOVERNANCE_PRESENT` — PeaRL governance block confirmed in CLAUDE.md

Use `pearl_get_promotion_readiness` to retrieve the most recent evaluation without triggering a new one.

Use `pearl_submit_evidence` to satisfy framework control gate rules (AIUC-1, OWASP LLM, etc.) by attesting to controls found in the codebase.

Use `pearl_confirm_claude_md` to satisfy the `CLAUDE_MD_GOVERNANCE_PRESENT` rule after writing the governance block to CLAUDE.md.

### 7b. Request Promotion

**MCP tool:** `pearl_request_promotion`
**REST endpoint:** `POST /api/v1/projects/{project_id}/promotions/request`

If gate evaluation passes, `pearl_request_promotion` creates a formal promotion request (an `ApprovalRequestRow` with `request_type = "promotion_gate"`). This requires human sign-off. After calling this tool, the agent must stop and await a human decision. Do not attempt to approve the request from an agent — `pearl_decide_approval` requires reviewer role and returns 403 for agent keys.

On approval, PeaRL advances `current_environment` on the `ProjectRow` and updates the `EnvironmentProfileRow` for the new environment.

Promotion history is available via `pearl_get_promotion_history` or `GET /api/v1/projects/{project_id}/promotions/history`.

### 7c. Pre-Promotion Contract Check

Before a promotion is approved, use `pearl_check_agent_contract` (supplying the `packet_id` from `pearl_submit_contract_snapshot`) to verify the agent team has stayed within its approved contract: budget limits, model restrictions, skill content hash, and MCP allowlist.

---

## 8. Approval Workflows

Any action that requires human judgment must go through PeaRL's approval workflow. Gates route decisions to humans — this is the design, not a failure state.

**MCP tool:** `pearl_request_approval`
**REST endpoint:** `POST /api/v1/approvals`

Request fields:
- `approval_request_id` — pre-generated ID matching `appr_[A-Za-z0-9_-]+`
- `project_id`
- `request_type` — `deployment_gate | auth_flow_change | network_policy_change | exception | remediation_execution | promotion_gate`
- `environment`
- `request_data` — context for the reviewer: what action was blocked and why

After calling `pearl_request_approval`, the agent must:
1. Record the returned `approval_request_id` and dashboard URL
2. Inform the user what was blocked and why
3. Stop — do not proceed until a human decides

**Polling:** `pearl_check_approval_status` — poll for the human decision. Do not use the `decide` endpoint from an agent key; it returns 403.

**Exceptions:** Use `pearl_create_exception` when a gate cannot be cleared through normal remediation and deliberate risk acceptance is required. Like approval requests, exceptions require human review — stop after calling this tool.

Human reviewers approve or reject via `POST /api/v1/approvals/{approval_request_id}/decide` with `{ "decision": "approve" | "reject", "decided_by": "...", "reason": "..." }`.

---

## 9. Workload Deregistration and Run Materialization

When an agent finishes its session, it deregisters its workload.

**REST endpoint:** `DELETE /api/v1/workloads/{svid}?frun_id={session_id}`

The `frun_id` query parameter is the session ID used when pushing cost entries to LiteLLM. When provided, PeaRL looks up the associated task packet and calls the factory run materializer, which aggregates:
- `total_cost_usd` — sum of all cost entries for the session
- `models_used` — list of distinct model identifiers
- `tools_called` — count of tool calls
- `duration_ms` — elapsed time from workload registration to deregistration
- `anomaly_flags` — open drift findings for this project and environment at the time of deregistration
- `outcome` — derived from the task packet status (`achieved | failed | abandoned`)

The result is stored as a `FactoryRunSummaryRow` with `frun_id` as its primary key.

Retrieve the summary with:

**MCP tool:** `pearl_get_run_summary`
**REST endpoint:** `GET /api/v1/workloads/run-summaries/{frun_id}`

If the workload deregisters without a `frun_id`, no factory run is materialized. Factory runs can also be materialized as a fallback when a task packet completes if `packet_data["run_id"]` is set.

---

## Allowance Profile Enforcement

If the workload was registered with an `allowance_profile_id`, agents can check whether a specific action is permitted before executing it:

**MCP tool:** `pearl_allowance_check`

This evaluates three enforcement layers:
- Layer 1 — baseline rules from the allowance profile
- Layer 2 — environment tier overrides
- Layer 3 — per-task extensions from the active task packet

Returns `allowed: true/false` with a reason string. Use this before any action that the profile might restrict.

---

## Agent Brief

For a structured summary of the project's current gate status, open task packets, and requirement statuses, use:

`GET /api/v1/projects/{project_id}/promotions/agent-brief`

This endpoint returns the current stage, next stage, gate evaluation results, open task packets, and per-rule requirement statuses — formatted for agent consumption without requiring multiple queries.
