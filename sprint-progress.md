# sprint-progress.md — Security Sprint Agent Status

The main session uses this file to coordinate PR merges in order.
Agents: update your row when you raise your PR. Do not modify other rows.

| Agent | Status | PR | Notes |
|---|---|---|---|
| auth-hardening | pr-raised | TBD | API key hashing upgraded to HMAC-SHA256 (auth.py:97, routes/auth.py:84, main.py:58-60). main.py:44 nosec added. integrations.py:215,341,427 stack trace exposure fixed. |
| server-audit-trail | pr-raised | https://github.com/r33n3/PeaRL/pull/9 | Open question in decisions.md: auto_pass field semantic ambiguity in gate.evaluated events (should it be renamed auto_pass_eligible?). |
| security-hardening | pr-raised | https://github.com/r33n3/PeaRL/pull/7 | All 4 items complete. Pre-existing test failures (153) are FileNotFoundError for PeaRL_spec/examples/ — not in scope. |
| security-validation | pr-raised | https://github.com/r33n3/PeaRL/pull/8 | Rebase on main after server-audit-trail merges to activate 4 xfail audit trail tests. Pre-existing HMAC bug in governance_telemetry.py documented in decisions.md. |

## Merge order
1. `server-audit-trail` — foundation, validation depends on its audit records
2. `security-hardening` — independent, can merge before or after server-audit-trail
3. `security-validation` — rebase on main after 1+2 merged

## Memory captures (agents fill in — main session writes to memory after merge)

If you made a non-obvious decision, found a gotcha, or discovered something future agents
should know — add it here before raising your PR.

| Agent | What to remember |
|---|---|
| server-audit-trail | HMAC signature on AuditEventRow uses settings.audit_hmac_key (PEARL_AUDIT_HMAC_KEY env var). GET /audit/events now requires auth (viewer+) and returns hmac_valid per event. All governance endpoints write server-side audit events. Constant-time hmac.compare_digest used for verification. |
| security-hardening | MCP audit events write to `/projects/{pid}/audit-events` HTTP endpoint (not direct DB) — MCPServer has no DB session. 153 pre-existing test failures are `FileNotFoundError: PeaRL_spec/examples/` in worktree (fixture gap, not regression). |
| security-validation | PEARL_LOCAL=1 doesn't set local_mode (correct var: PEARL_LOCAL_MODE). L4 tests patch it explicitly — same fix needed for pre-existing L1/L3 failures. governance_telemetry HMAC verify broken in SQLite (timezone strip on round-trip). |

## Memory updates (main session fills this after each merge)
<!-- Record what shipped and any open items that carry forward -->
