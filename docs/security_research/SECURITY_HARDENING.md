# PeaRL — Production Security Hardening Guide

**Audience:** Platform engineers and security reviewers deploying PeaRL
**Date:** 2026-03-01
**Related research:** [`pearl_autonomous_attack_research.md`](./pearl_autonomous_attack_research.md)

This guide covers operational controls that cannot be enforced purely in application
code. They must be applied by a human operator to the host environment.

---

## 1. Local Dev — Make `.env` Read-Only (Blocks L6)

The most impactful single change for local development. An autonomous agent with
file Write access can append `PEARL_LOCAL_REVIEWER=1` to `.env`, and nothing in the
application layer prevents it. Making `.env` read-only at the OS level stops the
Write tool cold — even if the agent constructs the correct content.

```bash
# Run once after creating your .env from .env.example
chmod 400 .env
```

**Why `400` and not `444`?** Mode `400` (owner read-only, no group/world) prevents
the agent from writing even if it runs as the same user, because the write bit is
removed for everyone. Mode `444` adds world-read which is unnecessary.

**After this change:** To edit `.env` yourself, temporarily restore write access:
```bash
chmod 600 .env   # restore user read+write
# make your edit
chmod 400 .env   # lock again
```

---

## 2. Install the PreToolUse Bash Guard Hook

The guard script at `scripts/pearl_bash_guard.py` intercepts every Bash command
Claude Code proposes and blocks only **PeaRL governance-specific bypass patterns**:

- Direct governance API calls via curl (`/approvals/*/decide`, `/exceptions/*/decide`)
- Shell commands that write `PEARL_LOCAL_REVIEWER` into any config file

**Intentionally NOT blocked** — these are needed for legitimate autonomous prototyping:
- `ps aux`, `pgrep` — debugging running processes
- `kill`, `pkill` — restarting dev servers
- `docker compose restart`, `docker restart` — container management
- `systemctl` — service management
- General `.env` writes (non-governance content)

The tradeoff is explicit: PeaRL hardens its own governance boundary without
restricting the autonomous coding workflows that make it useful as a prototyping
platform. Hard OS-level controls (see §1 and §3) cover the `kill`/restart vector
by making config tampering ineffective even if those commands run.

### Installation

Merge the following into your `~/.claude/settings.json`. If the file doesn't exist,
create it. If `hooks` already exists, merge the `PreToolUse` key into it.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/PeaRL/scripts/pearl_bash_guard.py"
          }
        ]
      }
    ]
  }
}
```

Replace `/path/to/PeaRL` with the absolute path to your repo. On Windows/WSL:
```
"command": "python /mnt/c/Users/YOUR_USER/Development/PeaRL/scripts/pearl_bash_guard.py"
```

### Verification

```bash
# Should exit 0 — ps/kill/docker allowed for legitimate prototyping:
echo '{"tool_input":{"command":"ps aux | grep uvicorn"}}' \
  | python3 scripts/pearl_bash_guard.py
echo '{"tool_input":{"command":"kill -HUP 12345"}}' \
  | python3 scripts/pearl_bash_guard.py
echo '{"tool_input":{"command":"docker compose restart myapp"}}' \
  | python3 scripts/pearl_bash_guard.py

# Should exit 0 — normal dev commands always allowed:
echo '{"tool_input":{"command":"pytest tests/ -q"}}' \
  | python3 scripts/pearl_bash_guard.py

# Should exit 2 (governance API bypass):
echo '{"tool_input":{"command":"curl -X POST http://localhost:8081/api/v1/approvals/appr_123/decide"}}' \
  | python3 scripts/pearl_bash_guard.py

# Should exit 2 (governance flag write):
echo '{"tool_input":{"command":"echo PEARL_LOCAL_REVIEWER=1 >> .env"}}' \
  | python3 scripts/pearl_bash_guard.py
```

---

## 3. Server User Separation (Blocks L6 in Shared Environments)

Run the PeaRL API server as a dedicated OS user (`pearl-svc`) that is separate from
the user account the agent runs under (`dev`). Then own `.env` by `pearl-svc` with
mode `400`. The agent's user cannot read or write it regardless of any code-level
permissions.

```bash
# Create service user (Linux)
sudo useradd -r -s /bin/false pearl-svc

# Own the .env by the service user
sudo chown pearl-svc:pearl-svc .env
sudo chmod 400 .env

# Run the API as pearl-svc
sudo -u pearl-svc PYTHONPATH=src uvicorn pearl.main:app --port 8081
```

The agent (running as your dev user) cannot read or write `.env`. Even if it
constructs the correct content and calls Write, the OS will return EACCES.

---

## 4. Production — Eliminate `.env` Entirely (Best Practice)

In production, don't ship a `.env` file at all. PeaRL's `config.py` uses Pydantic
`BaseSettings` which reads directly from environment variables. Inject `PEARL_*`
variables from your secrets platform instead:

| Platform | Mechanism |
|---|---|
| Kubernetes | `envFrom.secretRef` in the pod spec |
| AWS ECS | Secrets Manager → `secrets` in task definition |
| AWS Lambda | SSM Parameter Store via `AWS_SSM_PATH` |
| HashiCorp Vault | Vault Agent sidecar with env injection |
| Docker Compose (prod) | `environment:` block from CI secrets |

With no `.env` on disk there is nothing for the agent to tamper with. The attack
surface for L6 drops to zero.

---

## 5. CI Guardrail — Assert Local-Mode Flags Are Unset

`PEARL_LOCAL=1` and `PEARL_LOCAL_REVIEWER=1` must never be set in CI or production.
Add this assertion to `.github/workflows/pearl-gate.yml` (or your equivalent CI
workflow) in the environment validation step:

```yaml
- name: Assert governance flags are unset
  run: |
    if [ -n "$PEARL_LOCAL" ]; then
      echo "ERROR: PEARL_LOCAL is set — local-mode bypass is not allowed in CI"
      exit 1
    fi
    if [ -n "$PEARL_LOCAL_REVIEWER" ]; then
      echo "ERROR: PEARL_LOCAL_REVIEWER is set — reviewer bypass is not allowed in CI"
      exit 1
    fi
```

Place this step **before** any test or deploy steps so a misconfigured environment
fails fast.

---

## 6. Monitoring — Alert on `governance_access_denied` Events

PeaRL now emits a structured `WARNING` log event whenever an `AuthorizationError`
(HTTP 403) is raised. In production JSON-structlog mode the event looks like:

```json
{
  "level": "warning",
  "event": "governance_access_denied",
  "path": "/api/v1/approvals/appr_abc/decide",
  "method": "POST",
  "trace_id": "abc-123",
  "user_sub": "agent@example.com",
  "user_roles": ["operator"],
  "reason": "Insufficient scope"
}
```

### Alert Query (CloudWatch Logs Insights)

```sql
fields @timestamp, path, method, user_sub, user_roles, reason
| filter event = "governance_access_denied"
| sort @timestamp desc
| limit 100
```

### Alert Query (Datadog / Loki)

```
{service="pearl-api"} |= "governance_access_denied"
```

### Recommended Alert Threshold

Trigger a P2 alert if more than **3** `governance_access_denied` events occur from
the same `user_sub` within a 5-minute window — this indicates an agent is probing
the governance API rather than making incidental requests.

---

## Summary Checklist

| Action | Environment | Blocks |
|---|---|---|
| `chmod 400 .env` | Local dev | L6 config tampering |
| Install `pearl_bash_guard.py` PreToolUse hook | Any with Claude Code | L6, L7 |
| `disallowedBashCommands` in `.mcp.json` | Any with Claude Code | L7 (second line) |
| Server user separation (`pearl-svc`) | Shared/staging | L6 |
| No `.env` in production (use secrets manager) | Production | L6 |
| CI assertion: governance flags unset | CI/CD | L3, L5 |
| Alert on `governance_access_denied` log events | Production | Detection |
