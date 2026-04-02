# decisions.md — Cross-Agent Questions

Agents: if you need a decision from another agent or the human, write it here.
Do not guess. Do not block. Write the question and continue with what you can.
The human checks this file periodically during the sprint.

## Open Questions

<!-- Format: [agent-name] question -->

## Resolved

[security-validation] action_type strings — tests use "approval.decided" and "exception.created" as documented. Confirmed correct — server-audit-trail used the same strings.

[server-audit-trail] `gate.evaluated` audit event `auto_pass` field renamed to `auto_pass_eligible` — reflects gate row's trust-accumulation eligibility, not whether this specific evaluation triggered an auto-pass. Fixed in `gate_evaluator.py` details dict.

[security-validation] governance_telemetry HMAC verify broken in SQLite — root cause: `timestamp_dt.isoformat()` on write produced UTC-aware string (`+00:00`); SQLite strips timezone on round-trip so verify saw naive string. Fixed: normalize to naive UTC with `.replace(tzinfo=None)` before signing in `governance_telemetry.py`. L5 test should now pass (no longer xfail).
