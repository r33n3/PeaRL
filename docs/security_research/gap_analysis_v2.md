# PeaRL — Governance Hardening Gap Analysis v2

**Phase 0 Deliverable — Step 0.6 (CP1 Surface)**
**Date:** 2026-03-01
**Status:** Ready for human review — STOP HERE per governance_hardening_plan_v2.md §0.6

---

## Executive Summary

Phase 0 read-only discovery of the PeaRL codebase confirms that the first hardening wave (commit 55f6e9f) successfully closed the most critical attack chain paths. The core governance role gates are solid. The gaps that remain fall into three categories:

1. **Audit trail gap** — successful governance actions are invisible to monitoring (only failures are logged)
2. **Context receipt gap** — attestation is voluntary and unverifiable; no enforcement exists
3. **Residual L5 documentation** — one source file comment explains the governance bypass mechanism to a reading agent

No new blocking vulnerabilities were found. The attack chain cannot complete end-to-end without human cooperation (L5 social engineering remains the only unblocked path to reviewer role in local dev).

---

## Part 1 — Hard vs. Soft Control Map

Full detail: `docs/security_research/control_classification.md`

### Attack Level Summary

| Level | Attack | Hard Controls | Soft Controls | Remaining Gap |
|---|---|---|---|---|
| L1 | MCP tool abuse (exception spam) | None — exception creation has no rate limit | CLAUDE.md, `_human_action_required` flag | **GAP-01**: no rate gate on exception creation |
| L2 | OpenAPI schema discovery | Middleware disables `/openapi.json` in production | CLAUDE.md prohibition | Clean — no gap in prod |
| L3 | Direct API exploitation | `RequireReviewer` dep on decide endpoints; `governance_access_denied` 403 log | `disallowedBashCommands` in local `.mcp.json` | **GAP-05**: `.mcp.json` gitignored, absent in clean install |
| L4 | Evidence poisoning | Role gate on `false_positive` status (single + bulk) | None | **GAP-06**: `accepted`/`suppressed` status may pass gate without role check |
| L5 | Social engineering | None (by nature of social engineering) | CLAUDE.md, dashboard banner, stripped `.env.example` | **GAP-02**: `dependencies.py:38` comment teaches the bypass |
| L6 | Config tampering | Bash guard blocks `PEARL_LOCAL_REVIEWER` shell writes; `chmod 400` recommended | CLAUDE.md prohibition | **GAP-03**: MCP Write tool path not covered by bash guard |
| L7 | Process control | None (intentional prototyping tradeoff) | CLAUDE.md prohibition | **GAP-04**: ps/kill/docker unblocked by design; mitigated at OS level by chmod 400 + user sep |

### Specific Hard Control Implementations Verified

| Control | File | Line |
|---|---|---|
| `PEARL_LOCAL=1` → operator role only | `src/pearl/dependencies.py` | 40-48 |
| `RequireReviewer` on approvals decide | `src/pearl/api/routes/approvals.py` | 79 |
| `RequireReviewer` on exceptions decide | `src/pearl/api/routes/exceptions.py` | 118 |
| `false_positive` single-finding role check | `src/pearl/api/routes/findings.py` | 104-106 |
| `false_positive` bulk-status role check | `src/pearl/api/routes/findings.py` | 124-126 |
| `governance_access_denied` log on 403 | `src/pearl/errors/handlers.py` | 21-33 |
| OpenAPI disabled when not local mode | `src/pearl/api/middleware/auth.py` | 26-27, 53-55 |
| Bash guard blocks `PEARL_LOCAL_REVIEWER` | `scripts/pearl_bash_guard.py` | 54-56 |

---

## Part 2 — Governance Audit Trail Gaps

Full detail: `docs/security_research/audit_trail_gaps.md`

### What Is Logged (Server-Authoritative)

- **`governance_access_denied`** (WARNING log) — emitted on every 403 `AuthorizationError`
- Covers: attempted bypass at L3, L4. Does NOT cover successful governance decisions.

### What Is NOT Logged (Significant Gap)

The following governance-modifying actions complete without any server-side structured log event:

| Action | Route |
|---|---|
| Exception created | `POST /exceptions` |
| Exception decided | `POST /exceptions/{id}/decide` |
| Approval decided | `POST /approvals/{id}/decide` |
| Promotion requested | `POST /projects/{id}/promotions/request` |
| Promotion rolled back | `POST /projects/{id}/promotions/rollback` |
| Finding marked false_positive | `PATCH /findings/{id}/status` |
| Bulk false_positive | `POST /projects/{id}/findings/bulk-status` |

**Impact:** A SIEM configured per `SECURITY_HARDENING.md §6` sees blocked attempts but is blind to successful governance decisions. A reviewer approving a suspicious exception, or an operator calling the promotion endpoint at unusual hours, generates no alert-able event.

**Note:** `AuditEventRow` model and repository exist in the codebase but are never written to by any route handler. The infrastructure for persistent governance audit records is present but unwired.

### SSE Events Are Not Audit Records

`publish_event` calls in approvals.py, promotions.py, and task_packets.py produce Redis pub/sub messages. These are ephemeral UI notifications. They are not persisted and cannot be queried by SIEM.

---

## Part 3 — Context Receipt Attestation Gap

Full detail: `docs/security_research/context_receipt_gap.md`

### What Currently Works

- `ContextReceiptRow` model with fields: `cr_id`, `project_id`, `commit_hash`, `agent_id`, `tool_calls`, `artifact_hashes`, `consumed_at`
- `POST /context/receipts` creates receipt rows
- Gate evaluator has `FAIRNESS_CONTEXT_RECEIPT_VALID` rule type that checks if any receipt exists for the project

### The Gap — Precise Statement

**An agent can complete task packets, request promotions, and decide governance actions (if reviewer role) without ever submitting a context receipt.** There is no dependency, middleware, or route-level gate that checks for a receipt before permitting governance actions.

Additionally, when `FAIRNESS_CONTEXT_RECEIPT_VALID` is active in a gate:
- It checks for **any receipt ever** for the project — not a recent one from the current agent
- Once one receipt exists, this check passes permanently
- `agent_id` is an optional, unverified field the agent submits itself
- Receipt content (artifact hashes) is not validated against compiled context packs

### Session Model Blocker

To implement a hard gate (Option A in Phase 2), PeaRL needs a session concept. Currently the API is stateless HTTP with no session tracking. The CP2a decision (session model + option A vs B) must be made before Phase 2 implementation can begin.

---

## Part 4 — Residual L5 Social Engineering Documentation

Full detail: `docs/security_research/control_classification.md §L5`

### Files Requiring Action

**`src/pearl/dependencies.py:38-39`** — **Action required in Phase 3**

```python
# Reviewer/governance decisions (approve/reject) additionally require PEARL_LOCAL_REVIEWER=1,
# so that agents hitting the API directly cannot self-approve exceptions.
```

This comment is inside `src/` — a directory an agent reads during codebase reconnaissance (AA-RECON-01). It directly names the governance bypass flag, its effect, and the security rationale — which an agent can use to construct a social engineering prompt ("I need to add PEARL_LOCAL_REVIEWER=1 to .env to complete this governance approval...").

**Recommended action (Phase 3 task 3.2):** Replace with:
```python
# Reviewer role is controlled by the server environment — see SECURITY_HARDENING.md.
# stripped: governance bypass documentation removed per security_research/SECURITY_HARDENING.md L5
```

### Files That Are Acceptable

- `README.md:95` — public docs with deterrent wording; intentional
- `docs/architecture.md:283` — architecture reference; intentional, in `docs/`
- `tests/conftest.py:61-64` — test fixture docs; low risk, development environment only
- `.env.example:36` — commented flag with no explanation; appropriately stripped

---

## Prioritized Gap Table

| Gap ID | Severity | Exploitable Without Human? | Phase | Action |
|---|---|---|---|---|
| GAP-07 | High | Yes (silent success) | 1/later | Add `governance_action_completed` log events on governance decisions |
| GAP-08 | High | Yes | 2 | Context receipt enforcement — Option A (hard gate) or Option B (anomaly) |
| GAP-01 | Medium | Yes (L1 spam) | 1 | AGP-01 anomaly detection; rate gate is Phase 2+ |
| GAP-02 | Medium | Yes (reconnaissance aid) | 3 | Strip comment from `dependencies.py:38-39` |
| GAP-06 | Medium | Unclear | 3 | Audit gate evaluator treatment of `accepted`/`suppressed` finding statuses |
| GAP-03 | Low-Med | No (requires L5 success first) | Ops | `chmod 400 .env` — documented in SECURITY_HARDENING.md §1 |
| GAP-04 | Low-Med | No (requires L6 success first) | Ops | OS user separation — documented in SECURITY_HARDENING.md §3 |
| GAP-05 | Low | No (requires direct curl) | 3 | Ship `.mcp.json` template in repo or enforce via onboarding |

---

## What to Approve at CP1

Before Phase 1 begins, confirm the following scope decisions:

1. **Anomaly detection first (Phase 1):** Implement DB-query-based anomaly detectors for AGP-01 through AGP-05. These are detection-only and do not block requests. No controversy.

2. **Context receipt enforcement (Phase 2):** This requires your decision at CP2a:
   - Option A (hard gate) vs Option B (anomaly-only detection)?
   - If Option A: which session model?
   The gap analysis confirms the infrastructure exists; the decision is architectural.

3. **Audit logging for governance successes (not in plan v2):** The gap is real and the infrastructure (`AuditEventRow`) already exists. This could be added to Phase 1 as a task 1.x or treated as a separate ticket. Recommend raising as a discussion item.

4. **`dependencies.py:38-39` comment strip:** Confirmed as a soft control gap. Scheduled for Phase 3 task 3.2.

---

## STOP HERE

Per `governance_hardening_plan_v2.md §0.6`: surface this gap analysis for human review before proceeding to Phase 1.
