# SPEC — PeaRL Dark Factory Governance Layer

> Last updated: 2026-03-31
> Status: Draft
> Context: Extends PeaRL v1.1.0 with enforcement hooks required for lights-out agent factory operations

---

## Overview

This spec covers the five governance primitives PeaRL needs to act as the trust accumulation and agent elevation layer for the Secure Agent Dark Factory. The existing PeaRL platform handles promotion gates, findings, approvals, and MCP tooling. This layer adds the missing pre-runtime enforcement, execution tracking, workload identity mapping, progressive trust accumulation, and behavioral drift ingestion.

The goal: **agents go from registration to production fast and secure, with human approval required only until trust is earned — after which gates flip to auto-pass.**

Reference architecture: `C:\Users\bradj\Development\Dark_Factory_Research\ARCHITECTURE.md` v0.3

---

## Goals

- Enforce agent compliance profiles deterministically before tool calls (not after the fact at gates)
- Track agent execution phase through task lifecycle — enables stateless agent replacement
- Map live workloads (SPIRE SVIDs) to task packets for control room visibility
- Accumulate deployment reliability signal per gate — flip to auto-pass after threshold is reached
- Ingest behavioral drift findings from the control plane as first-class PeaRL findings that affect gate status

---

## Constraints

- `pearl_allowance_check` is a deterministic enforcement call — no LLM involved, latency must be sub-50ms
- Gates are project-scoped — replacement agents inherit project trust history, not per-instance
- MASS is pre-deployment only — dynamic MASS at runtime is out of scope
- Control plane owns crash detection and triage — PeaRL receives findings, not events
- Auto-pass threshold is pattern-based (reliable deployment count), not time-based or admin-toggled
- Agent must never self-approve — RBAC constraint from existing PeaRL core
- `PEARL_LOCAL=1` is test harness only — enforcement hooks must be testable in SQLite mode

---

## Out of Scope (this version)

- Agent Registry / Marketplace (P5 from dark factory roadmap)
- SPIRE SVID issuance — PeaRL consumes SVIDs, does not issue them
- LiteLLM cost reporter middleware (separate integration)
- Dynamic MASS runtime scanning
- Fine-grained per-tool-call logging at model inference level
- deepagents-harbor evaluation integration

---

## Architecture

```
Dark Factory Agent (deepagents / LangGraph)
    │
    │  Before every tool call:
    ├──▶ pearl_allowance_check(action, agent_id, task_packet_id)
    │         │  AllowanceProfileRow → 3-layer merge → {allowed, reason}
    │         └──▶ PeaRL API: POST /allowance-profiles/{id}/check
    │
    │  Task lifecycle:
    ├──▶ generateTaskPacket()  →  trace_id generated, execution_phase = "planning"
    ├──▶ PATCH /task-packets/{id}/phase  →  planning → coding → testing → review → complete
    │
    │  Workload identity:
    ├──▶ POST /workloads/register  →  SVID → task_packet_id mapping
    │
    │  On completion:
    ├──▶ completeTaskPacket()
    └──▶ MASS pre-deployment scan → PeaRL findings → gate evaluation

Control Plane (coordinator agents)
    │
    ├──▶ Acute violation (cost 10x, blast radius exceeded)
    │         → Hard stop in control plane (no PeaRL round-trip)
    │         → POST /findings  (source: control_plane, type: behavioral_drift, subtype: acute)
    │
    └──▶ Trend signal (token budget creeping, tool frequency shift)
              → POST /findings  (source: control_plane, type: behavioral_drift, subtype: trend)
              → trend findings aggregate against gate trust confidence

PeaRL Gate Evaluation
    │
    ├──▶ PromotionGateRow.pass_count increments on each successful human-approved promotion
    ├──▶ When pass_count >= auto_pass_threshold AND no open trend findings → gate.auto_pass = true
    └──▶ Auto-pass gates skip human approval queue entirely
```

**New models:** `AllowanceProfileRow`, `WorkloadRow` (adds to `task_packet.py` fields)
**Modified models:** `TaskPacketRow` (execution_phase, phase_history), `PromotionGateRow` (auto_pass, pass_count, auto_pass_threshold)
**New routes:** `/allowance-profiles`, `/workloads`
**New MCP tool:** `pearl_allowance_check`
**New finding type:** `behavioral_drift` (subtypes: `acute`, `trend`)

---

## Features

### Feature: Agent Allowance Profiles

**Status:** Planned
**Priority:** Critical

Three-layer per-agent scope model enforced deterministically before every tool call. Enforcement is a simple policy check — no LLM in the hot path.

**Layer 1 — Baseline rules (per agent type, stored in AllowanceProfileRow):**
- `blocked_commands: list[str]` — shell commands never permitted
- `blocked_paths: list[str]` — filesystem paths never writable
- `pre_approved_actions: list[str]` — tool calls that never need approval
- `model_restrictions: list[str]` — which LLM models this agent may use
- `budget_cap_usd: float` — max spend before auto-pause

**Layer 2 — Environment overrides:**
- `env_tier: permissive | standard | strict | locked` mapped to sandbox/dev/preprod/prod

**Layer 3 — Per-task extensions (from task packet, derived from worktrees.yaml):**
- `allowed_paths: list[str]` — paths this specific task may touch
- `pre_approved_commands: list[str]` — commands pre-approved for this sprint

Resolved allowance = baseline merged with env override merged with task extension.

**Acceptance criteria:**
- [ ] `AllowanceProfileRow` model with all Layer 1 fields + `profile_id: alp_` prefix
- [ ] `POST /allowance-profiles` — create profile (admin/operator role)
- [ ] `GET /allowance-profiles/{id}` — read profile
- [ ] `PUT /allowance-profiles/{id}` — update profile
- [ ] `POST /allowance-profiles/{id}/check` — evaluate `{action, agent_id, task_packet_id}` → `{allowed: bool, reason: str, layer: str}` in < 50ms
- [ ] `GET /task-packets/{id}/allowance` — resolved 3-layer merged allowance for a task
- [ ] `pearl_allowance_check(action, agent_id, task_packet_id)` MCP tool registered and tested
- [ ] Layer 3 extensions sourced from task packet `allowed_paths` field (must add to TaskPacketRow)
- [ ] Check endpoint returns which layer triggered the deny (aids debugging)
- [ ] PEARL_LOCAL=1 SQLite-compatible (no JSON operators)
- [ ] Tests: blocked command denied, pre-approved action passes, env tier escalation correct, task extension grants access

**Key files:**
- `src/pearl/db/models/allowance_profile.py` — new model (create)
- `src/pearl/api/routes/allowance_profiles.py` — new routes (create)
- `src/pearl/repositories/allowance_profile_repo.py` — new repo (create)
- `src/pearl/mcp/tools.py` — add `pearl_allowance_check` tool
- `src/pearl/mcp/server.py` — register new tool route
- `src/pearl/db/models/task_packet.py` — add `allowed_paths`, `pre_approved_commands` fields
- `tests/test_allowance_profiles.py` — new test file (create)

---

### Feature: Execution Phase Primitive

**Status:** Planned
**Priority:** High

Task packets track current execution phase, enabling stateless agent replacement. A replacement agent picks up at the recorded phase — no trust chain restart needed since gates are project-scoped.

Phases: `planning` → `coding` → `testing` → `review` → `complete` | `failed`

**Acceptance criteria:**
- [ ] `execution_phase: str` added to `TaskPacketRow` (default: `planning`)
- [ ] `phase_history: JSON` added to `TaskPacketRow` — array of `{phase, timestamp, agent_id}` entries
- [ ] `PATCH /task-packets/{id}/phase` endpoint — validates phase transition is legal (no backward jumps except to `failed`)
- [ ] `generateTaskPacket` MCP tool response includes `execution_phase` field
- [ ] Phase history appended on each transition (not replaced)
- [ ] `GET /task-packets/{id}` response includes `execution_phase` and `phase_history`
- [ ] DB migration for existing rows (default `planning` for all open packets)
- [ ] Tests: valid transition accepted, illegal backward transition rejected, `failed` reachable from any phase

**Key files:**
- `src/pearl/db/models/task_packet.py` — add `execution_phase`, `phase_history`
- `src/pearl/api/routes/task_packets.py` — add PATCH /phase endpoint
- `src/pearl/db/migrations/versions/002_add_execution_phase_to_task_packets.py` — new migration (create)
- `tests/test_task_packets.py` — extend with phase transition tests

---

### Feature: Trust Accumulation & Auto-Pass Gates

**Status:** Planned
**Priority:** High

Gates accumulate reliability signal over successful deployments. When a gate has passed `auto_pass_threshold` times with no open trend findings, it flips to `auto_pass = true`. Human approval queue is skipped entirely for auto-pass gates. Auto-pass is revoked if a trend finding opens against the project.

**Acceptance criteria:**
- [ ] `auto_pass: bool` (default `false`) added to `PromotionGateRow`
- [ ] `pass_count: int` (default `0`) added to `PromotionGateRow` — incremented on each successful human-approved promotion through this gate
- [ ] `auto_pass_threshold: int` (default `5`) added to `PromotionGateRow` — configurable per gate
- [ ] Gate evaluator checks `auto_pass` flag — if true and all rule checks pass, approval request is auto-decided `approved` without entering the human queue
- [ ] `pass_count` incremented only on human-approved promotions (not auto-pass promotions — earned trust only)
- [ ] Auto-pass revoked (set to `false`) when a `behavioral_drift` finding of subtype `trend` is opened against the project
- [ ] Auto-pass restored (re-evaluated) when trend finding is resolved
- [ ] `GET /projects/{id}/gates` response includes `auto_pass`, `pass_count`, `auto_pass_threshold` fields
- [ ] Admin can manually set `auto_pass_threshold` via `PATCH /gates/{id}` (admin role only)
- [ ] DB migration for existing gate rows
- [ ] Tests: gate flips to auto-pass at threshold, auto-pass skips queue, trend finding revokes auto-pass, human-only promotions increment counter

**Key files:**
- `src/pearl/db/models/promotion.py` — add auto_pass, pass_count, auto_pass_threshold to PromotionGateRow
- `src/pearl/services/promotion/gate_evaluator.py` — auto-pass logic
- `src/pearl/api/routes/promotions.py` — expose fields in gate response
- `src/pearl/db/migrations/versions/003_add_trust_accumulation_to_gates.py` — new migration (create)
- `tests/test_promotion_gate.py` — extend with auto-pass tests

---

### Feature: Workload Registry

**Status:** Planned
**Priority:** Medium

Maps active SPIRE SVIDs to live task packets and allowance profiles. Provides control room dashboard visibility into what is running, what it is allowed to do, and when it was last seen. SSE stream emits workload join/leave events.

**Acceptance criteria:**
- [ ] `WorkloadRow` model: `svid`, `task_packet_id`, `allowance_profile_id`, `agent_id`, `registered_at`, `last_seen_at`, `status: active|inactive`
- [ ] ID prefix: `wkld_`
- [ ] `POST /workloads/register` — register SPIRE SVID to task packet (service_account role)
- [ ] `POST /workloads/{svid}/heartbeat` — update `last_seen_at` (service_account role)
- [ ] `DELETE /workloads/{svid}` — deregister on agent exit (service_account role)
- [ ] `GET /workloads` — list active workloads with task packet and allowance profile summary
- [ ] SSE stream emits `workload.registered` and `workload.deregistered` events
- [ ] Workloads with no heartbeat for > 5 minutes auto-set to `inactive` (background check or on-read)
- [ ] `GET /dashboard` includes active workload count
- [ ] Tests: register, heartbeat, deregister, inactive timeout, SSE event emission

**Key files:**
- `src/pearl/db/models/workload.py` — new model (create)
- `src/pearl/api/routes/workloads.py` — new routes (create)
- `src/pearl/repositories/workload_repo.py` — new repo (create)
- `src/pearl/api/routes/stream.py` — add workload events
- `src/pearl/api/routes/dashboard.py` — include workload count
- `tests/test_workloads.py` — new test file (create)

---

### Feature: Behavioral Drift Signal Path

**Status:** Planned
**Priority:** Medium

Provides a typed finding path from the control plane into PeaRL. Separates acute violations (immediate hard stop, already handled by control plane) from trend signals (pattern-based drift that accumulates as gate risk). Trend findings influence trust accumulation — open trend findings block auto-pass gate flip.

**Two subtypes:**

| Subtype | Trigger | Control Plane Action | PeaRL Effect |
|---|---|---|---|
| `acute` | Cost 10x, blast radius exceeded, illegal tool sequence | Hard stop already applied | Finding logged, patch cycle triggered |
| `trend` | Token budget creeping, tool frequency shifting over runs | No stop — coordinator flags pattern | Blocks auto-pass gate flip, accumulates risk signal |

**Acceptance criteria:**
- [ ] `behavioral_drift` added as a valid `source` value in `FindingRow` (alongside `pearl_scan`, `mass`, etc.)
- [ ] Finding `category` field accepts `drift_acute` and `drift_trend` as valid categories
- [ ] `POST /findings` accepts `source: behavioral_drift` with `metadata.subtype: acute | trend`
- [ ] Open `drift_trend` findings for a project block gate auto-pass evaluation (gate evaluator checks)
- [ ] `drift_trend` finding resolution triggers re-evaluation of gate auto-pass eligibility
- [ ] `GET /projects/{id}/findings?source=behavioral_drift` returns all drift findings
- [ ] MCP tool `ingestFindings` accepts `behavioral_drift` source without modification
- [ ] Dashboard finding summary includes behavioral drift count separately from scan findings
- [ ] Tests: acute finding created, trend finding blocks auto-pass, resolving trend re-enables auto-pass evaluation

**Key files:**
- `src/pearl/db/models/finding.py` — add `behavioral_drift` to source enum/validation
- `src/pearl/models/enums.py` — add drift finding categories
- `src/pearl/services/promotion/gate_evaluator.py` — trend finding check blocks auto-pass
- `src/pearl/api/routes/findings.py` — ensure source validation accepts new type
- `src/pearl/api/routes/dashboard.py` — behavioral drift count in summary
- `tests/test_behavioral_drift.py` — new test file (create)

---

## End-to-End Validation Scenario

**Scenario: "First Agent to Production"**

This scenario exercises all five features together. It is the acceptance test for the complete dark factory governance layer.

```
Step 1 — Register allowance profile
  POST /allowance-profiles
  Body: { blocked_commands: ["rm -rf", "curl"], blocked_paths: ["/etc", "/root"],
          pre_approved_actions: ["read_file", "write_file", "ls"],
          model_restrictions: ["claude-sonnet-4-6"], budget_cap_usd: 5.0,
          env_tiers: { standard: {...}, strict: { budget_cap_usd: 2.0 } } }
  Assert: profile_id returned (alp_ prefix)

Step 2 — Create project + task packet
  POST /projects  →  proj_ id
  POST /task-packets (via generateTaskPacket MCP)  →  trace_id generated, execution_phase = "planning"
  Assert: task packet has trace_id, execution_phase = "planning", allowed_paths populated

Step 3 — Register workload
  POST /workloads/register  { svid: "spiffe://factory/agent/worker-1", task_packet_id, allowance_profile_id }
  Assert: wkld_ id returned, SSE emits workload.registered event

Step 4 — Simulate tool calls via allowance check
  POST /allowance-profiles/{id}/check  { action: "read_file", agent_id, task_packet_id }
  Assert: { allowed: true, reason: "pre_approved_actions", layer: "baseline" }

  POST /allowance-profiles/{id}/check  { action: "rm -rf /tmp", agent_id, task_packet_id }
  Assert: { allowed: false, reason: "blocked_commands", layer: "baseline" }

  GET /task-packets/{id}/allowance
  Assert: resolved 3-layer profile returned

Step 5 — Advance execution phases
  PATCH /task-packets/{id}/phase  { phase: "coding" }   → accepted
  PATCH /task-packets/{id}/phase  { phase: "testing" }  → accepted
  PATCH /task-packets/{id}/phase  { phase: "planning" } → 422 (illegal backward transition)
  PATCH /task-packets/{id}/phase  { phase: "review" }   → accepted
  Assert: phase_history has 3 entries with timestamps

Step 6 — Inject trend drift finding from control plane
  POST /findings  { source: "behavioral_drift", category: "drift_trend",
                    title: "Token budget trending +15% per run",
                    project_id, metadata: { subtype: "trend", runs_observed: 5 } }
  Assert: finding created, gate auto-pass blocked

Step 7 — MASS pre-deployment scan + gate evaluation
  POST /scan-targets  →  run scan
  POST /projects/{id}/promotions/evaluate
  Assert: gate evaluation includes behavioral_drift finding count
  Assert: auto_pass = false (trend finding open)

Step 8 — Human approval (first promotion)
  POST /approvals  →  decision: approved
  Assert: pass_count increments to 1 on gate
  Assert: auto_pass still false (threshold = 5, count = 1)

Step 9 — Resolve trend finding + re-evaluate
  PATCH /findings/{id}  { status: "resolved" }
  Assert: gate re-evaluated, auto_pass eligibility restored (pending count threshold)

Step 10 — Deregister workload
  DELETE /workloads/{svid}
  Assert: workload status = inactive, SSE emits workload.deregistered
```

**All assertions passing = governance layer is working end-to-end.**

---

## Known Tech Debt

- `test_mcp.py` hardcodes tool count (currently 41) — update to 42 when `pearl_allowance_check` is added
- `PEARL_LOCAL=1` SQLite mode has no JSON column operators — all new JSON fields need SQLite-safe queries
- Existing `PromotionGateRow` has no migration versioning — gate rule sync on startup is a workaround
- `trace_id` on `TaskPacketRow` exists but is not yet exposed in all MCP tool responses

---

## Open Questions

- [ ] Should `auto_pass_threshold` have a per-org default configurable via `OrgEnvironmentConfigRow`, or is per-gate config sufficient?
- [ ] Should workload heartbeat timeout (5 min) be configurable, or is a sensible fixed default acceptable for v1?
- [ ] Does `pearl_allowance_check` need to be callable as a standalone HTTP endpoint (for non-MCP agents) or MCP-only for now?
