# PeaRL — Context Receipt Enforcement Design

**Phase 2 Deliverable — Task 2.1**
**Date:** 2026-03-01
**Decision:** Option B (soft gate + anomaly signal)
**Authorized by:** Human review at CP2a

---

## 1. Current State

`POST /context/receipts` creates a `ContextReceiptRow` recording that an agent claimed to
have consumed a context package. Fields: `cr_id`, `project_id`, `commit_hash`, `agent_id`
(optional, unverified), `tool_calls`, `artifact_hashes`, `consumed_at`.

Receipt submission is **voluntary**. No route gate, dependency, or middleware checks for a
receipt before permitting governance actions.

Full technical analysis: `docs/security_research/context_receipt_gap.md`

---

## 2. The Gap

An agent can call `POST /task-packets/{id}/complete` and `POST /projects/{id}/promotions/request`
without having submitted any context receipt. There is no server-side enforcement of the
attestation promise that PeaRL's architecture makes: that agents operated on current,
PeaRL-compiled governance context.

---

## 3. Options Considered

### Option A — Hard Gate

Add a `require_context_receipt` dependency to `complete_task_packet` and `request_promotion`.
If no receipt exists for the current session → 403 `context_receipt_required`.

**Pros:** Closed-loop attestation chain. Analyst can verify "did it have context?" from DB.
**Cons:** Breaking change for all existing workflows that don't submit receipts. No automatic
receipt submission exists in the MCP tools today — agents would fail with 403s immediately.
Requires a session model definition before implementation. Blocks autonomous coding until
the MCP workflow is proven to auto-submit receipts reliably.

### Option B — Soft Gate + Anomaly Signal ✅ (Selected)

Allow all governance actions. Wire AGP-05 (from Phase 1) as a background task post-response
on the same endpoints. If no receipt is found in the recency window → `governance_anomaly_detected`
AGP-05 emitted to logs. Nothing blocks.

**Pros:** Zero friction for existing workflows. Provides real detection signal immediately.
Allows 30 days of data collection before deciding whether Option A is viable.
**Cons:** Attestation is observable, not enforceable. A deliberate attacker can suppress
AGP-05 by submitting a receipt (even with fabricated content) before acting.

---

## 4. Decision: Option B

**Rationale:**

Receipt submission is not yet a reliable, automatic step in the agent workflow. The MCP
`submitContextReceipt` tool exists but is a manual call — no route handler or worker
auto-submits a receipt on the agent's behalf. Enforcing Option A today would break all
autonomous coding workflows that don't already include an explicit receipt submission step,
producing 403s that look identical to a governance attack but are actually legitimate
workflows.

Option B is the correct first step:
1. Detection signal is live immediately
2. Legitimate workflows are uninterrupted
3. 30 days of AGP-05 data informs whether Option A is viable and what session window to use

Option A should be reconsidered after:
- Confirming that `compileContext` (or equivalent MCP workflow entry point) auto-submits a receipt
- Running 30 days of AGP-05 data and confirming it fires rarely for legitimate workflows
- Defining the session model (recommendation: `(jwt_sub, project_id)` + 24h rolling window)

---

## 5. Implementation (Option B)

AGP-05 is wired as a `BackgroundTasks` post-response call on:

| Endpoint | File | Wiring |
|---|---|---|
| `POST /task-packets/{id}/complete` | `src/pearl/api/routes/task_packets.py` | Phase 1 ✅ |
| `POST /projects/{id}/promotions/request` | `src/pearl/api/routes/promotions.py` | Phase 2 ✅ |

The request is not blocked. The response is returned normally. AGP-05 runs after
the response is sent and emits `governance_anomaly_detected` if no receipt is found.

---

## 6. Path to Option A

When the following conditions are met, revisit Option A:

1. **Receipt auto-submission is wired**: `compileContext` or task packet claim automatically
   calls `POST /context/receipts` without agent intervention.
2. **30 days of AGP-05 data**: confirm detection rate for legitimate workflows is < 5%.
3. **Session model decided**: `(jwt_sub, project_id)` + 24h rolling window is the
   recommended starting point. Document the decision here when it is made.
4. **Grace period planned**: deploy with a `PEARL_RECEIPT_GATE_ENABLED` flag defaulting to
   `false`, configurable by operators, so teams can opt in before it becomes mandatory.
