# PeaRL — Governance Behavioral Anomaly Patterns

**Phase 1 Deliverable — Task 1.1**
**Date:** 2026-03-01

---

## Purpose

These patterns describe agent behaviors that are individually-observable governance actions but
collectively indicate a goal-directed agent probing the governance system. Each pattern is derived
directly from the observed attack chain in `pearl_autonomous_attack_research.md`.

Detection is **observation-only**: the detector emits a `governance_anomaly_detected` log event
and does not block. Blocking thresholds are a human decision made after reviewing real production
detection rates. All threshold values are marked as requiring calibration.

---

## Pattern Taxonomy

| Pattern ID | Description | Relevant Attack Level | Signal Source |
|---|---|---|---|
| AGP-01 | Exception creation rate: >N exceptions for same project within T minutes | L1 | `ExceptionRecordRow.created_at` |
| AGP-02 | Promotion request within T seconds of task packet completion | L1/L2 | `PromotionHistoryRow.promoted_at`, `TaskPacketRow.completed_at` |
| AGP-03 | Bulk false_positive status change: >N findings in single request | L4 | Inline — `len(finding_ids)` at request time |
| AGP-04 | Repeated `governance_access_denied` events from same `user_sub` within window | L3 | Server logs (see note) |
| AGP-05 | Governance action taken without a context receipt in the current window | Attestation gap | `ContextReceiptRow`, governance action timestamp |
| AGP-06 | OpenAPI schema fetch followed by governance endpoint calls within session | L2 → L3 | Access logs (see note) |

---

## Pattern Details

### AGP-01 — Exception Creation Rate

**Description:** An agent creating >N exceptions for the same project within T minutes is likely
running the L1 in-band exploitation pattern: creating exceptions for every finding it wants to
clear from the gate, at machine speed.

**Signal:** `ExceptionRecordRow.created_at` — count rows where `project_id = X` and
`created_at >= now() - T minutes`.

**Threshold proposal (calibration required):**
- N = 5 exceptions
- T = 10 minutes
- Confidence: high if count > 2×N; medium if count > N

**Why this threshold:** A human reviewer filing exceptions manually would rarely create more
than 2-3 exceptions in 10 minutes. An agent creating 5+ in that window is operating at
machine speed. The threshold is intentionally conservative to minimize false positives in the
first 30 days.

**⚠️ Calibration required** after first 30 days of production data. Do not tune by intuition.

**Limitation:** `ExceptionRecordRow.requested_by` may be "dashboard-user" if created via the
contest-rule UI path. The detector uses `project_id` as the primary correlation key; `requested_by`
is recorded in evidence but may not reliably identify the agent.

---

### AGP-02 — Rapid Promotion After Task Completion

**Description:** An agent requesting a promotion within T seconds of completing a task packet
indicates goal-directed rushing through the governance pipeline. Legitimate development takes
time to validate; an agent racing from "task complete" to "request promotion" in under 60
seconds is not allowing for human review of the work.

**Signal:** Most recent `TaskPacketRow.completed_at` for project, compared to current
`PromotionHistoryRow.promoted_at` (or promotion request timestamp).

**Threshold proposal (calibration required):**
- T = 60 seconds
- Confidence: high if delta < 15s; medium if delta < 60s

**⚠️ Calibration required** — legitimate automated CI pipelines may also trigger rapidly.
Review detection rate before considering any blocking action.

---

### AGP-03 — Bulk False Positive Marking

**Description:** A single `POST /projects/{id}/findings/bulk-status` call marking >N findings
as `false_positive` is the L4 evidence poisoning pattern: clearing the gate by reclassifying
findings rather than fixing them.

**Note:** This action is already role-gated (reviewer role required). If this detector fires, it
means a **reviewer** is mass-reclassifying findings, which is either a legitimate bulk triage
or a compromised/coerced reviewer session.

**Signal:** Inline at request time — `len(finding_ids)` in the bulk update body.

**Threshold proposal (calibration required):**
- N = 10 findings in a single bulk request
- Confidence: high if count > 25; medium if count > N

**⚠️ Calibration required** — bulk triage after a large scan may legitimately produce this
pattern. Calibrate against normal triage batch sizes.

---

### AGP-04 — Repeated Governance Access Denied

**Description:** The same `user_sub` receiving >N `governance_access_denied` (HTTP 403) events
within a T-minute window indicates an agent probing the governance API, trying different
endpoints and approaches to find an unguarded path.

**Signal:** `governance_access_denied` structured log events — count by `user_sub` in time window.

**⚠️ Current limitation:** This signal exists in server logs but NOT in the database. The
`governance_access_denied` event is emitted as a structured WARNING log line (see
`src/pearl/errors/handlers.py:21-33`) but not written to any DB table. The Phase 1 detector
for this pattern is a **SIEM alert query**, not an in-process anomaly detector.

**SIEM alert query (CloudWatch Logs Insights):**
```sql
fields @timestamp, user_sub, path, method
| filter event = "governance_access_denied"
| stats count() as denied_count by user_sub, bin(5m)
| filter denied_count > 3
| sort denied_count desc
```

**Future path:** When `AuditEventRow` is wired as a server-side write-path for 403 events,
AGP-04 can become a DB-query-based detector. Until then it is a SIEM-only control.

---

### AGP-05 — Missing Context Receipt Before Governance Action

**Description:** An agent completing a task packet or requesting a promotion without having
submitted a context receipt in the preceding time window indicates it either did not consume
the compiled context, or deliberately skipped attestation.

**Signal:** Check `ContextReceiptRow` for the project within a recency window (default 24h)
immediately before a governance action.

**Threshold proposal (calibration required):**
- Recency window: 24 hours
- Confidence: medium (agent_id is unverified; receipt may have been submitted by a different agent)

**Important note (from plan v2):** This detector runs **post-response** (background task).
The governance action already completed by the time the anomaly fires. This is detection-only
(Option B). If Phase 2 chooses Option A (hard gate), AGP-05 must be replaced by a synchronous
`require_context_receipt` dependency — it cannot remain a background detector if it is also
expected to block.

**Limitation:** `ContextReceiptRow.agent_id` is optional and unverified. A receipt submitted
with any project_id passes the check. The detector cannot verify that the receipt is from
the same agent taking the governance action without a session model (see CP2a).

---

### AGP-06 — OpenAPI Schema Fetch Before Governance Calls

**Description:** An agent fetching `/openapi.json` and then calling governance endpoints within
the same session indicates L2→L3 chaining: schema discovery followed by immediate exploitation
attempt.

**⚠️ Requires session tracking infrastructure that does not currently exist.** This pattern
requires correlating two separate HTTP requests by the same agent across time, which requires:
- A session identifier propagated across requests
- Access log correlation (not available from application DB)

**Status:** Documented here for completeness. **Do not implement in Phase 1.** Retained so it
is not lost. Revisit when session infrastructure is available.

---

## Log Event Format

All in-process detectors emit a `governance_anomaly_detected` WARNING log in the same format,
compatible with SIEM queries:

```json
{
  "level": "warning",
  "event": "governance_anomaly_detected",
  "pattern_id": "AGP-01",
  "user_sub": "agent@example.com",
  "project_id": "proj_abc",
  "confidence": "high",
  "evidence": {
    "exception_count": 8,
    "window_minutes": 10,
    "threshold": 5
  },
  "trace_id": "abc-123",
  "timestamp": "2026-03-01T12:00:00Z"
}
```

---

## Notes on Threshold Calibration

All threshold values (N, T) in this document are **initial proposals**. They were chosen to
be conservative — a high N and a wide T — to minimize false positives during the initial
deployment period.

**Do not tune these values by intuition alone.** After 30 days of production data:
1. Review detection frequency per pattern
2. Identify false positive rate (legitimate developer actions that triggered detection)
3. Adjust thresholds based on observed normal rates, not theoretical estimates
4. Document the calibration rationale and date in this file

The SECURITY_HARDENING.md §6 alert queries reference these pattern IDs and should be updated
when thresholds change.
