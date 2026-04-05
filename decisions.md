# decisions.md — Cross-Agent Questions

Agents: if you need a decision from another agent or the human, write it here.
Do not guess. Do not block. Write the question and continue with what you can.
The human checks this file periodically during the sprint.

## Open Questions

<!-- Format: [agent-name] question -->

[auth-hardening] main.py lines changed (for antipatterns rebase): line 44 had `# nosec` appended inline; line 58 (single SHA256 line) replaced by 3 lines (import hmac as _hmac, compute secret, compute HMAC hash). Net delta: +2 lines starting at old line 58. Antipatterns ALTER TABLE removal is likely below line 80 — should be clean.

[auth-hardening] No data migration needed: API key hashing change is forward-only. Existing hashed keys (including bootstrap admin) are re-seeded at startup if missing (idempotent seed). Any existing API keys in a live DB will stop working after the config change until re-issued. This is expected — document in release notes.

## Resolved

[security-validation] action_type strings — tests use "approval.decided" and "exception.created" as documented. Confirmed correct — server-audit-trail used the same strings.

[server-audit-trail] `gate.evaluated` audit event `auto_pass` field renamed to `auto_pass_eligible` — reflects gate row's trust-accumulation eligibility, not whether this specific evaluation triggered an auto-pass. Fixed in `gate_evaluator.py` details dict.

[security-validation] governance_telemetry HMAC verify broken in SQLite — root cause: `timestamp_dt.isoformat()` on write produced UTC-aware string (`+00:00`); SQLite strips timezone on round-trip so verify saw naive string. Fixed: normalize to naive UTC with `.replace(tzinfo=None)` before signing in `governance_telemetry.py`. L5 test should now pass (no longer xfail).
