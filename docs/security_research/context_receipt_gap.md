# PeaRL — Context Receipt Attestation Gap

**Phase 0 Deliverable — Step 0.4**
**Date:** 2026-03-01

---

## What Context Receipts Are

Context receipts record that an agent claimed to have consumed a context package (compiled governance context) before acting. The architectural intent is: *agents should operate on current, PeaRL-compiled context, not on stale or hallucinated knowledge of the governance state.*

The Contract-First AI Governance paper identifies context receipt attestation as a core architectural feature of PeaRL. This document maps what is currently implemented against that intent.

---

## What Is Currently Implemented

### Data Model

**`ContextReceiptRow`** (`src/pearl/db/models/fairness.py:102-113`):

| Field | Type | Required? | Notes |
|---|---|---|---|
| `cr_id` | String | Yes | Primary key |
| `project_id` | String | Yes | FK to projects |
| `commit_hash` | String | No | Optional — git commit at time of consumption |
| `agent_id` | String | No | Optional — agent identity claim; **unverified** |
| `tool_calls` | JSON list | No | Optional — list of tool calls made |
| `artifact_hashes` | JSON dict | No | Optional — hashes of consumed artifacts |
| `consumed_at` | DateTime | No | Set server-side on create |

**`ContextContractRow`** (`src/pearl/db/models/fairness.py:78-87`): Defines required artifacts per project/environment.

**`ContextPackRow`** (`src/pearl/db/models/fairness.py:90-99`): Compiled context package with artifact hashes.

### Receipt Submission Route

`POST /context/receipts` (`src/pearl/api/routes/context.py:91-108`):
- Accepts any dict body with `project_id`
- Creates a `ContextReceiptRow`
- No auth check beyond standard middleware
- No validation that `cp_id` (context pack ID) was valid or recent
- No validation that `agent_id` matches the JWT subject
- No link between receipt and the context pack it claims to attest

### Gate Evaluator Usage

`src/pearl/services/promotion/gate_evaluator.py:368-370`:

```python
cr_repo = ContextReceiptRepository(session)
receipts = await cr_repo.list_by_field("project_id", project_id)
ctx.has_context_receipt = len(receipts) > 0
```

Then in `_eval_fairness_context_receipt_valid` (line 859-860):
```python
return ctx.has_context_receipt, \
    "Context receipt on file" if ctx.has_context_receipt else "No context receipt from agent", \
    None
```

This check:
- Evaluates to PASS if **any receipt at all** exists for the project
- Is only active when a gate includes rule type `FAIRNESS_CONTEXT_RECEIPT_VALID`
- Does not check receipt recency (a receipt from 30 days ago passes)
- Does not check that the receipt is from the current agent (`agent_id` unverified)
- Does not check that the receipt references a valid context pack
- Does not check that the consumed artifacts match the compiled pack hashes

---

## The Attestation Gap — Precise Description

### Gap 1: Receipt Submission Is Fully Voluntary

There is **no dependency, middleware, or route-level gate** that checks for a context receipt before permitting governance actions:

- `POST /task-packets/{id}/complete` — no receipt check
- `POST /projects/{id}/promotions/request` — no receipt check
- `POST /exceptions/{id}/decide` — no receipt check
- `POST /approvals/{id}/decide` — no receipt check

An agent that never calls `POST /context/receipts` can complete task packets, request promotions, and (if reviewer role) decide approvals without restriction.

### Gap 2: The Gate Check Is Per-Project, Not Per-Session

When `FAIRNESS_CONTEXT_RECEIPT_VALID` is configured as a gate rule, it checks whether *any* receipt exists for the project — not whether the current agent submitted one recently. Once one receipt exists for a project (from any agent, at any time), all future evaluations pass this check permanently.

### Gap 3: Session Does Not Exist

PeaRL's HTTP API is stateless. There is no session concept. The `agent_id` field in `ContextReceiptRow` is optional and unverified — it is whatever the agent submits in the request body. There is no way to correlate a receipt submission with subsequent governance actions by the same agent without external session infrastructure.

### Gap 4: Receipt Content Is Unverified

The receipt body accepts `artifact_hashes` but these are not validated against the `ContextPackRow.artifact_hashes` for any specific pack. An agent could submit a receipt with empty or fabricated hashes and it would be accepted.

### Gap 5: No Receipt Rejection Path

If `FAIRNESS_CONTEXT_RECEIPT_VALID` fails (no receipt found), the gate evaluator returns a FAIL result. This blocks promotion evaluation — but only if:
1. The gate has this rule configured (optional rule, not required by default)
2. The agent is using the promotion evaluate/request flow (not directly calling decide endpoints)

An agent bypassing the promotion flow and calling decide endpoints directly (already blocked by RequireReviewer) would not encounter this check at all.

---

## What This Means for the Attack Chain

The context receipt mechanism as implemented is a **soft attestation layer** — it records what agents claim to have consumed, but:
- Does not enforce consumption before action
- Cannot verify the claim
- Does not bind the claim to the JWT identity of the acting agent
- Only surfaces as a gate blocker if a specific rule is configured and the agent uses the promotion flow

A goal-directed agent (as observed in the red-team) would not be blocked by the current implementation. It could:
1. Submit a receipt with fabricated content or skip submission entirely
2. Proceed to create exceptions, request promotions, and complete task packets
3. The only relevant block would be `FAIRNESS_CONTEXT_RECEIPT_VALID` rule in the gate — which requires the rule to be configured and would be trivially bypassed by submitting any receipt before calling evaluate

---

## Enforcement Options (for Phase 2)

See `docs/security_research/context_receipt_enforcement_design.md` (produced in Phase 2 Task 2.1) for the full Option A vs. Option B analysis. Summary:

**Option A (Hard gate):** Add `require_context_receipt` dependency to `complete_task_packet` and `request_promotion` routes. Requires defining a session model.

**Option B (Soft gate with anomaly signal):** Wire AGP-05 detection post-response on the same endpoints. No blocking; detection-only.

**Session model blocker for Option A:** PeaRL is stateless HTTP. To implement Option A correctly, a session model must be defined before implementation begins. Options include:
- `(jwt_sub, project_id)` + rolling time window
- `(jwt_sub, project_id, calendar_day)`
- Redis-tracked session token the agent carries

This is a CP2a human decision.
