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

## 6. Monitoring — Governance Security Alerts

PeaRL emits two families of structured WARNING log events for governance security monitoring.

### 6.1 — `governance_access_denied` (HTTP 403 on governance endpoints)

Emitted by `src/pearl/errors/handlers.py` whenever an `AuthorizationError` is raised:

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

**CloudWatch alert — repeated governance probe (AGP-04):**
```sql
fields @timestamp, user_sub, path, method
| filter event = "governance_access_denied"
| stats count() as denied_count by user_sub, bin(5m)
| filter denied_count > 3
| sort denied_count desc
```

**Datadog / Loki — all 403 events:**
```
{service="pearl-api"} |= "governance_access_denied"
```

**Recommended threshold:** P2 alert if more than **3** events from the same `user_sub`
within a 5-minute window. ⚠️ Calibration required after 30 days of production data.

---

### 6.2 — `governance_anomaly_detected` (Behavioral Anomaly Detection)

Emitted by `src/pearl/security/anomaly_detector.py` as a background task after
governance actions. Pattern taxonomy: `docs/security_research/anomaly_patterns.md`.

```json
{
  "level": "warning",
  "event": "governance_anomaly_detected",
  "pattern_id": "AGP-01",
  "project_id": "proj_abc",
  "user_sub": "agent@example.com",
  "confidence": "high",
  "evidence": { "exception_count": 8, "window_minutes": 10, "threshold": 5 },
  "trace_id": "abc-123"
}
```

**CloudWatch — any anomaly detection:**
```sql
fields @timestamp, pattern_id, project_id, user_sub, confidence, evidence
| filter event = "governance_anomaly_detected"
| sort @timestamp desc
| limit 100
```

**CloudWatch — high-confidence only:**
```sql
fields @timestamp, pattern_id, project_id, user_sub, evidence
| filter event = "governance_anomaly_detected" and confidence = "high"
| sort @timestamp desc
```

**Datadog / Loki:**
```
{service="pearl-api"} |= "governance_anomaly_detected"
```

**Alert thresholds by pattern** (⚠️ calibration required after 30 days):

| Pattern | Description | Alert on |
|---|---|---|
| AGP-01 | Exception creation rate | Any detection at medium+ confidence |
| AGP-02 | Rapid promotion after task completion | Any high-confidence detection |
| AGP-03 | Bulk false_positive marking | Any detection (reviewer action — always notable) |
| AGP-04 | Repeated 403s | SIEM only — see §6.1 query above |
| AGP-05 | Missing context receipt | Any detection (informational — tune after 30 days) |

---

---

## 7. Context Receipt Enforcement (Option B — Soft Gate)

PeaRL's architectural promise is that agents operated on current, PeaRL-compiled
governance context before taking governance actions. `submitContextReceipt` records
this attestation voluntarily — there is no hard gate today.

**Current state (Option B):** AGP-05 fires as a background detection signal after
`POST /task-packets/{id}/complete` and `POST /projects/{id}/promotions/request` when
no context receipt exists within the prior 24 hours. The action is not blocked.

**Path to Option A (hard gate):** Three conditions must be met before enforcing:
1. `compileContext` (or equivalent workflow entry point) auto-submits a receipt
2. 30 days of AGP-05 data confirms false-positive rate for legitimate workflows is < 5%
3. Session model decided — recommended: `(jwt_sub, project_id)` + 24h rolling window

Design note: `docs/security_research/context_receipt_enforcement_design.md`

**Monitoring query for AGP-05:**
```sql
fields @timestamp, project_id, user_sub, evidence
| filter event = "governance_anomaly_detected" and pattern_id = "AGP-05"
| sort @timestamp desc
```

Use AGP-05 detections to track how often agents operate without submitting a receipt.
Once the false-positive rate for legitimate workflows is confirmed low, enable Option A
via the `PEARL_RECEIPT_GATE_ENABLED` config flag (to be added when Option A is built).

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
| Alert on `governance_access_denied` log events | Production | Detection (L3–L4 failures) |
| Alert on `governance_anomaly_detected` log events | Production | Detection (AGP-01–05) |
| Run `pearl_context_drift_check.py` in CI | CI/CD | L5 documentation drift |
| Monitor AGP-05 detections (30-day window) | Production | Informs Option A gate decision |
