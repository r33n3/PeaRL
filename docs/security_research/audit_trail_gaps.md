# PeaRL — Governance Audit Trail Gaps

**Phase 0 Deliverable — Step 0.3**
**Date:** 2026-03-01

---

## What Counts as an Audit Trail?

For this analysis an "audit trail" entry requires:
1. **Server-authoritative** — produced by the server, not submitted by the agent
2. **Persistent** — survives server restart; not ephemeral (SSE pub/sub)
3. **Structured** — machine-parseable (log line with context fields or DB row)
4. **Contains:** actor identity, action, resource, timestamp, outcome

---

## Currently Emitting Structured Events

### Server Log: `governance_access_denied`

**Location:** `src/pearl/errors/handlers.py:21-33`
**Trigger:** Any `AuthorizationError` (HTTP 403)
**Fields:** `path`, `method`, `trace_id`, `user_sub`, `user_roles`, `reason`
**Persistence:** Structured log line (to stdout/SIEM in production)
**Coverage:** L3 and L4 failures only — captures attempted bypass, not successful action

```json
{
  "level": "warning",
  "event": "governance_access_denied",
  "path": "/api/v1/approvals/appr_abc/decide",
  "user_sub": "agent@example.com",
  "user_roles": ["operator"]
}
```

### SSE Events (Ephemeral — NOT audit trail)

**Location:** `src/pearl/api/routes/approvals.py:130`, `promotions.py:47`, `task_packets.py:200`
**Trigger:** Approval decided, gate evaluated, task packet completed
**Persistence:** Redis pub/sub only — no database record, no log line
**Assessment:** These are real-time UI notifications. They are NOT audit records. If Redis restarts or no subscriber is connected, the event is lost. Not suitable for SIEM or compliance.

### Agent-Submitted Telemetry (NOT server-authoritative)

**Location:** `src/pearl/api/routes/governance_telemetry.py`, `ClientAuditEventRow`
**Trigger:** Agent pushes events via `POST /projects/{id}/audit-events`
**Persistence:** `ClientAuditEventRow` in database
**Assessment:** Agent-submitted. An agent can submit false, missing, or misleading events. Not a server-authoritative audit trail for governance actions. Useful for agent observability but cannot be trusted as the security record.

---

## Silent Governance Actions (No Server-Side Audit Record)

These are governance-modifying actions that create or change DB rows but emit no server-authoritative structured log event on **success**:

| Action | Route | What changes | Missing audit record |
|---|---|---|---|
| Exception created | `POST /exceptions` | `ExceptionRow` created with `status=pending` | No log event; no `AuditEventRow`; only DB row |
| Exception decided (approved/rejected) | `POST /exceptions/{id}/decide` | `ExceptionRow.status` updated | No success log; `governance_access_denied` only on 403 failure |
| Approval request created | `POST /approvals/requests` | `ApprovalRequestRow` created | No log event |
| Approval decided | `POST /approvals/{id}/decide` | `ApprovalRequestRow.status` updated; `ApprovalDecisionRow` created | SSE event only (ephemeral); no log line on success |
| Promotion requested | `POST /projects/{id}/promotions/request` | `ApprovalRequestRow` + optionally `PromotionHistoryRow` | No log event |
| Promotion rolled back | `POST /projects/{id}/promotions/rollback` | `PromotionHistoryRow` created with `type=rollback` | No log event |
| Finding marked false_positive | `PATCH /findings/{id}/status` | `FindingRow.status` updated | No log event |
| Bulk false_positive | `POST /findings/bulk-status` | Multiple `FindingRow.status` updated | No log event |
| Task packet claimed | `POST /task-packets/{id}/claim` | `TaskPacketRow.status` updated | Agent telemetry only |
| Task packet completed | `POST /task-packets/{id}/complete` | `TaskPacketRow.status` updated | Agent telemetry only |
| Context receipt submitted | `POST /context/receipts` | `ContextReceiptRow` created | No log event; no validation |

---

## AuditEventRow — Exists But Is Not Wired

The `AuditEventRow` model (`src/pearl/db/models/fairness.py:116-124`) and `AuditEventRepository` (`src/pearl/repositories/fairness_repo.py`) exist in the codebase. The `/audit/events` query route exists. But **no code path automatically creates `AuditEventRow` entries** for governance actions. The repository is defined but unused as a write path in any route handler.

This means the audit query endpoints (`GET /audit/events`, `GET /audit/events/resource/{id}`) return empty results unless an external process writes to this table directly — which no code does.

---

## Anomaly Detection Implications

The absence of server-side audit records for governance successes means:

- **AGP-01** (exception creation rate) — can be detected via `ExceptionRow` DB queries, not log events
- **AGP-02** (promotion immediately after task completion) — can be detected via `PromotionHistoryRow` + `TaskPacketRow` timestamps
- **AGP-03** (bulk false_positive) — can be detected via `FindingRow` status field, but no timestamp of when status was changed (no `updated_at` column visible in FindingRow)
- **AGP-04** (repeated 403s) — already covered by `governance_access_denied` log ✅
- **AGP-05** (no context receipt before governance action) — requires cross-referencing `ContextReceiptRow` against governance action timing; both are available in DB but not linked
- **AGP-06** (OpenAPI fetch before governance endpoint calls) — requires access log correlation; not currently available

**Implication for Phase 1:** Anomaly detectors for AGP-01, AGP-02, AGP-03 must query DB tables directly. They cannot rely on log events because those events don't exist for successful governance actions.

---

## Alert Coverage Assessment

| Alert type | Current coverage |
|---|---|
| Agent attempts and is blocked (403) | ✅ `governance_access_denied` log |
| Agent successfully approves exception | ❌ No server log — only DB change |
| Agent creates N exceptions rapidly | ❌ No log — DB-only |
| Agent marks N findings false_positive | ❌ No log — DB-only |
| Agent requests promotion | ❌ No log — DB-only |
| Agent submits context receipt | ❌ No log |
| Reviewer approves promotion | ❌ No log — only ephemeral SSE |

**The monitoring section in SECURITY_HARDENING.md §6 covers only the 403 case.** All successful governance decisions are currently invisible to a SIEM.

---

## Recommendations

1. **Phase 1 anomaly detection must be DB-query-based**, not log-event-based, for AGP-01 through AGP-03 and AGP-05.
2. **Phase 1 or later: add server-side success logging** for the high-value governance actions: exception decided, approval decided, promotion requested. Emit `governance_action_completed` structured WARNING events analogous to `governance_access_denied`.
3. **Wire `AuditEventRow`**: The model and repository already exist. Creating `AuditEventRow` entries in the exception/approval/promotion decide routes would give PeaRL a persistent tamper-resistant audit record for governance decisions.
4. **SSE events are not a substitute for audit logging.** If SSE event reliability matters, persist to DB before publishing.
