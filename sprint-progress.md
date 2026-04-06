# sprint-progress.md — Agent Completion Status

The main session uses this file to coordinate PR merges in order.
Agents: update your row when you raise your PR. Do not modify other rows.

| Agent | Status | PR | Notes |
|---|---|---|---|
| agent-registry | in-progress | — | — |
| trust-verdict | in-progress | — | — |

## Merge order
1. `agent-registry` — self-contained, no shared file conflicts with trust-verdict
2. `trust-verdict` — rebase on main after agent-registry merges (picks up router.py, __init__.py, tools.py, server.py additions)

## Memory captures (agents fill in — main session writes to memory after merge)

If you made a non-obvious decision, found a gotcha, or discovered something future agents
should know — add it here before raising your PR.

| Agent | What to remember |
|---|---|
| agent-registry | — |
| trust-verdict | — |

## Memory updates (main session fills this after each merge)
<!-- Record what shipped and any open items that carry forward -->
