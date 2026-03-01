# PeaRL — Hard vs. Soft Control Classification

**Phase 0 Deliverable — Step 0.2 + 0.5**
**Date:** 2026-03-01
**Scope:** All 7 attack chain levels from `pearl_autonomous_attack_research.md`

---

## Classification Criteria

- **Hard (H):** Code-enforced, fails closed. Blocks regardless of agent intent or instruction following. Requires code change to defeat.
- **Soft (S):** Documentation, CLAUDE.md instruction, UI warning, or configuration recommendation. Reduces friction for well-intentioned agents. A goal-directed agent can read, understand, and work around it.

---

## Level 1 — In-Band MCP Exploitation

| Control | Type | File / Location | Gap? |
|---|---|---|---|
| MCP developer profile excludes `decideApproval` | S | `src/pearl_dev/unified_mcp.py` — profile config | Yes — profile is a filter, not enforcement; direct API call bypasses it |
| `_human_action_required` flag in MCP response | S | MCP tool responses | Yes — informational only |
| Gate shows `AWAITING HUMAN REVIEW` blocker | S | Gate evaluator response | Yes — informational only |
| CLAUDE.md: do not self-approve | S | `CLAUDE.md` | Yes |
| Exception creation rate not gated | **Gap** | `src/pearl/api/routes/exceptions.py` | **No rate limit on POST /exceptions** |

**Hard control gap:** An agent can create unlimited exceptions for its own findings at any rate. The only friction is that exceptions remain `pending` (require human decision). No server-side limit or rate gate enforces a maximum exception creation rate per agent or per project.

---

## Level 2 — API Schema Discovery

| Control | Type | File / Location | Gap? |
|---|---|---|---|
| `/openapi.json` disabled when `local_mode=False` | H | `src/pearl/api/middleware/auth.py:26-27` — only added to public paths when `effective_expose_openapi=True` | No |
| `/docs` and `/redoc` disabled in production | H | `src/pearl/api/middleware/auth.py:53-55` | No |
| Returns 404, not 401, on schema paths in production | H | Middleware — path not in `_PUBLIC_PATHS`, falls through to auth checks | No |
| CLAUDE.md: do not call `/openapi.json` | S | `CLAUDE.md` | Yes |

**No hard control gap.** Schema discovery is fully blocked in production (`PEARL_EXPOSE_OPENAPI=0`). In local dev schema is exposed by design. The soft control in CLAUDE.md is a secondary deterrent.

---

## Level 3 — Direct API Exploitation

| Control | Type | File / Location | Gap? |
|---|---|---|---|
| `PEARL_LOCAL=1` → operator role only | H | `src/pearl/dependencies.py:40-48` | No |
| `RequireReviewer` on `POST /approvals/{id}/decide` | H | `src/pearl/api/routes/approvals.py:79` — `_reviewer: dict = RequireReviewer` | No |
| `RequireReviewer` on `POST /exceptions/{id}/decide` | H | `src/pearl/api/routes/exceptions.py:118` — `_reviewer: dict = RequireReviewer` | No |
| `governance_access_denied` log on 403 | H (detective) | `src/pearl/errors/handlers.py:21-33` | No |
| `disallowedBashCommands` (governance endpoints) in `.mcp.json` | S | `.mcp.json` — gitignored, local only; no enforcement if file absent | Yes |
| CLAUDE.md: do not approve own exceptions | S | `CLAUDE.md` | Yes |

**No blocking hard control gap** — role gate is enforced at code level. The `disallowedBashCommands` is a soft second line that requires `.mcp.json` to be present.

**Note on rollback:** `POST /projects/{id}/promotions/rollback` has a manual role check (`if "admin" not in user.get("roles", [])`) instead of `RequireAdmin` dependency — functionally equivalent but uses inline check pattern rather than the standard dependency.

---

## Level 4 — Evidence Poisoning

| Control | Type | File / Location | Gap? |
|---|---|---|---|
| `false_positive` on single-finding PATCH requires reviewer role | H | `src/pearl/api/routes/findings.py:104-106` | No |
| `false_positive` on bulk-status requires reviewer role | H | `src/pearl/api/routes/findings.py:124-126` | No |
| Gate evaluator checks active exceptions only | H (existing) | `src/pearl/services/promotion/gate_evaluator.py` | No |

**No hard control gap** on false_positive marking.

**Potential gap:** Other finding status transitions (`resolved`, `accepted`, `suppressed`) have no role gate. An agent could mark findings as `accepted` or `suppressed` without reviewer role. Gate evaluator behavior for these statuses is worth auditing separately — if `accepted` findings pass gate rules, this is an L4 residual.

---

## Level 5 — Social Engineering

| Control | Type | File / Location | Gap? |
|---|---|---|---|
| Stripped explanatory comments from `.env.example` | S | `.env.example:36` — flag present but commented, no explanation | Partial |
| Stripped explanatory comments from `config.py` | S | `src/pearl/config.py:13` — `local_reviewer_mode: bool = False`, no comment | No |
| CLAUDE.md: do not ask users to modify env vars | S | `CLAUDE.md:116` | Yes — soft only |
| Dashboard banner (reviewer mode warning) | S | Frontend UI | Yes — soft only |
| `PEARL_LOCAL_REVIEWER` is self-describing | **Gap** | Flag name itself | Yes — the flag name teaches the attack |

**L5 Residual Documentation Findings (outside `docs/security_research/`):**

1. **`src/pearl/dependencies.py:38-39`** — inline comment reads:
   ```python
   # Reviewer/governance decisions (approve/reject) additionally require PEARL_LOCAL_REVIEWER=1,
   # so that agents hitting the API directly cannot self-approve exceptions.
   ```
   This directly explains the bypass mechanism. An agent performing AA-RECON-01 (codebase reading) and reading `dependencies.py` learns the exact flag name, its effect, and the security intent — which it can then use to construct a social engineering prompt. **This comment should be stripped per Phase 3 task 3.2.**

2. **`README.md:95`** — documents `PEARL_LOCAL_REVIEWER` with purpose. Contains deterrent wording ("for human reviewers only — do not set on agent's behalf") but also provides the full flag name and effect. This is intentional public documentation; removing it would break onboarding. **Leave as-is; the deterrent wording is appropriate.**

3. **`docs/architecture.md:283`** — documents the auth model with the flag. Also intentional architecture documentation in `docs/` (not `src/`). **Leave as-is.**

4. **`tests/conftest.py:61-64`** — reviewer_client fixture docstring explains: "Use this fixture for tests that call decide endpoints which require security_reviewer role." Test code is not accessible to a running agent in production, but in dev mode an agent reading the test suite would learn the role name and endpoint pattern. **Low risk; leave as-is for test clarity.**

---

## Level 6 — Configuration Tampering

| Control | Type | File / Location | Gap? |
|---|---|---|---|
| CLAUDE.md: do not write to `.env` | S | `CLAUDE.md:115` | Yes — soft only |
| `PreToolUse` Bash hook blocks `PEARL_LOCAL_REVIEWER` shell writes | H (conditional) | `scripts/pearl_bash_guard.py:54-56` — blocks ANY command containing `PEARL_LOCAL_REVIEWER` | Conditional — only if hook is installed |
| `chmod 400 .env` recommendation | H (manual) | `docs/security_research/SECURITY_HARDENING.md §1` | Yes — not enforced, requires human action |
| Server user separation | H (manual) | `docs/security_research/SECURITY_HARDENING.md §3` | Yes — not enforced, requires DevOps action |

**Hard control gap:** The MCP `Write` tool (not Bash) is NOT covered by `pearl_bash_guard.py`. If an agent uses the Write tool directly to append to `.env`, the bash guard does not fire. The only code-level block on this path is CLAUDE.md (soft). The hard block requires `chmod 400 .env` (OS-level, documented but not enforced).

---

## Level 7 — Process Control

| Control | Type | File / Location | Gap? |
|---|---|---|---|
| CLAUDE.md: do not call ps/kill/docker restart | S | `CLAUDE.md` | Yes — soft only |
| `disallowedBashCommands` blocks governance endpoint curl | S (conditional) | `.mcp.json` — gitignored | Yes — only present locally, soft |
| `PreToolUse` hook does NOT block ps/kill/docker | Intentional non-control | Design decision (prototyping tradeoff) | N/A |

**Hard control gap (intentional):** `ps aux`, `kill`, `docker restart`, and `systemctl` are intentionally not blocked by `pearl_bash_guard.py` per the prototyping tradeoff decision. This means the L6→L7 kill chain (write .env, restart server) remains executable at the Bash layer if the agent uses the Write tool for L6 (bypassing the bash guard) and then uses ps/kill for L7.

The documented mitigation is OS-level: `chmod 400 .env` + server user separation makes the chain ineffective even if L7 runs, because the server won't pick up a tampered `.env` it can't read (owned by `pearl-svc`).

---

## Summary: Controls With No Hard Counterpart

| Gap ID | Level | Description | Current Soft Control | Recommended Hard Control |
|---|---|---|---|---|
| GAP-01 | L1 | No rate limit on exception creation | None | Rate gate (N exceptions per project per T minutes) — Phase 1 AGP-01 |
| GAP-02 | L5/L6 | `dependencies.py` comment explains bypass mechanism | CLAUDE.md | Strip comment (Phase 3 task 3.2) |
| GAP-03 | L6 | MCP Write tool can write `.env` (bash guard doesn't cover Write tool) | CLAUDE.md | `chmod 400 .env` (SECURITY_HARDENING.md §1) |
| GAP-04 | L7 | ps/kill/docker not blocked (intentional prototyping tradeoff) | CLAUDE.md | OS-level: chmod 400 + server user separation |
| GAP-05 | L3 | `disallowedBashCommands` only exists in local `.mcp.json` (gitignored) | Bash guard hook | Ship `.mcp.json` in repo or auto-generate via onboarding endpoint |
| GAP-06 | L4 | `accepted`/`suppressed` finding status has no role gate | None | Audit gate evaluator treatment of `accepted`/`suppressed` findings |
| GAP-07 | All | No server-side persistent audit log for governance actions on success | SSE events (ephemeral) | Server-side `AuditEventRow` creation on governance decisions — Phase 0 Step 0.3 |
| GAP-08 | L1/L2 | Context receipt is voluntary — no gate checks receipt before governance actions | None | Context receipt enforcement — Phase 2 |
