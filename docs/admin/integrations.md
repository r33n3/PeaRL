# PeaRL Admin Guide — Integrations

This guide covers how PeaRL connects to external tools (SonarQube, Snyk, Jira, Slack, etc.), how auth credentials are managed, and the full lifecycle of an integration — from registration to finding ingestion.

---

## Architecture Overview

Integrations in PeaRL are **org-level** (shared across all projects) or **project-level** (scoped to one project).
The Settings UI manages org-level integrations. Project-level integrations are managed via the API.

```
PeaRL API
  └── IntegrationEndpointRow (DB)
        ├── base_url         — target system URL
        ├── adapter_type     — "sonarqube", "snyk", "jira", etc.
        ├── auth_config      — JSON blob: { auth_type, raw_token | bearer_token_env, ... }
        └── labels           — adapter-specific options (e.g. project_keys)
              │
              ▼
        IntegrationService
              │
              ▼
        SourceAdapter.pull_findings()   →  NormalizedFinding[]  →  FindingRepository
```

No server restart is required to add or modify integrations. PeaRL resolves credentials at each connection attempt.

---

## Credential Storage Modes

PeaRL supports two modes for storing integration credentials. Both are configured from the admin panel — no config file or server env change needed for the **direct token** mode.

### Mode 1 — Direct Token (Local / Dev)

The token is stored in the PeaRL database as `raw_token` inside the `auth_config` JSON column.

- **Pros**: Zero server-side setup. Paste the token in the UI, click Save, done.
- **Cons**: Token lives in the database in plaintext. Acceptable for local SQLite instances; not recommended for shared or production databases.
- **When to use**: Local development, internal tooling, single-tenant deployments where DB access is already restricted.

### Mode 2 — Env Var Reference (Production)

The token is stored as an environment variable on the server. PeaRL only stores the variable **name** (`bearer_token_env`), not the value.

- **Pros**: Secret never written to the database. Rotate by updating the env var and rolling the deployment — no PeaRL config change.
- **Cons**: Requires access to set env vars on the server (or update a Kubernetes secret).
- **When to use**: Shared environments, production deployments, any setup with database access auditing.

> **Future direction:** A secrets manager backend (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault) is the recommended long-term path for production. See [Secret Store Roadmap](#secret-store-roadmap) below.

### Priority Logic

When both `raw_token` and `bearer_token_env` are set, the env var takes precedence:

```
if bearer_token_env is set AND os.environ[bearer_token_env] is non-empty:
    use env var value
else if raw_token is set:
    use raw_token
else:
    no auth header (connection will fail with 401)
```

This means you can migrate from direct token to env var by simply setting the env var — no database update required.

---

## Adding an Integration

### Via Admin Panel (Settings → Integrations)

1. Go to **Settings → Integrations**
2. Find the adapter category (Security Scanning, Issue Tracking, etc.)
3. Click **+** and select the integration type
4. Fill in:
   - **Base URL** — the target system's URL (e.g. `http://sonarqube.internal:9000`)
   - **API Token** — paste the token directly (stored in DB, no restart needed)
   - **Token Env Var** — *optional* — enter the server env var name for production deployments
5. Click **Save**, then **Test** to verify connectivity

### Via API

```bash
curl -X POST http://localhost:8081/api/v1/integrations \
  -H "Authorization: Bearer $PEARL_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "SonarQube Production",
    "adapter_type": "sonarqube",
    "integration_type": "source",
    "category": "security_scanning",
    "base_url": "https://sonarqube.internal",
    "auth_config": {
      "auth_type": "bearer",
      "raw_token": "squ_xxxx"
    }
  }'
```

For env var mode, replace `raw_token` with `bearer_token_env`:
```json
"auth_config": {
  "auth_type": "bearer",
  "bearer_token_env": "SONARQUBE_TOKEN"
}
```

---

## Testing an Integration

```bash
curl -X POST http://localhost:8081/api/v1/integrations/{endpoint_id}/test \
  -H "Authorization: Bearer $PEARL_ADMIN_TOKEN"
```

Returns:
```json
{ "success": true, "message": "SonarQube connection OK (status: UP)" }
```

---

## Pulling Findings Manually

Findings are pulled automatically by the scan scheduler (every 60 s).
To trigger an immediate pull for a specific project:

```bash
curl -X POST http://localhost:8081/api/v1/projects/{project_id}/integrations/{endpoint_id}/pull \
  -H "Authorization: Bearer $PEARL_ADMIN_TOKEN"
```

---

## Updating Credentials (No Restart Needed)

### Direct Token rotation

1. Settings → Integrations → Edit the integration
2. Paste the new token in **API Token**
3. Click Save → Test

### Env Var rotation

1. Update the env var on the server (or update the Kubernetes secret)
2. For Kubernetes: roll the deployment (`kubectl rollout restart deployment/pearl-api`)
3. Click Test in the UI to confirm the new value is being read

---

## Supported Adapters

| Adapter | Type | Auth | Notes |
|---------|------|------|-------|
| `sonarqube` | source | bearer token | See [sonarqube.md](sonarqube.md) |
| `snyk` | source | bearer token | |
| `semgrep` | source | bearer token | |
| `trivy` | source | bearer token | |
| `github` | source | bearer token | Personal access token or GitHub App |
| `gitlab` | source | bearer token | |
| `jira` | source + sink | bearer token | Also needs `project_key` label |
| `linear` | source + sink | bearer token | |
| `slack` | sink | webhook URL | Paste Incoming Webhook URL as Base URL |
| `teams` | sink | webhook URL | |
| `pagerduty` | sink | webhook URL | |
| `webhook` | sink | webhook URL | Generic HTTP endpoint |

---

## Auth Config Field Reference

These fields go into the `auth_config` JSON object stored in the DB:

| Field | Type | Description |
|-------|------|-------------|
| `auth_type` | string | `"bearer"`, `"api_key"`, `"basic"`, `"none"` |
| `raw_token` | string | Direct token value — local/dev only |
| `bearer_token_env` | string | Server env var name holding the bearer token |
| `api_key_env` | string | Server env var name holding an API key |
| `header_name` | string | Custom header for API key auth (default: `Authorization`) |
| `username_env` | string | Server env var for basic auth username |
| `password_env` | string | Server env var for basic auth password |

---

## Secret Store Roadmap

Storing tokens in the database (even encrypted) is not ideal for high-compliance environments.
The planned long-term path:

1. **Phase 1 (current)** — `raw_token` in DB + env var reference. Acceptable for local and small deployments.
2. **Phase 2** — Encrypted `raw_token` at rest using a PeaRL-managed key (`PEARL_SECRET_KEY` env var + AES-GCM). The DB stores ciphertext; decryption happens in memory at connection time.
3. **Phase 3** — Pluggable secrets backend:
   - `secret_ref: "vault://secret/pearl/sonarqube-token"` → HashiCorp Vault
   - `secret_ref: "arn:aws:secretsmanager:..."` → AWS Secrets Manager
   - `secret_ref: "azure-kv://vault/secret/..."` → Azure Key Vault

This work is tracked as a future roadmap item. For now:
- **Local dev**: use `raw_token` in the admin panel
- **Production**: use env var references + Kubernetes Secrets or similar platform secret management
- **High compliance**: use env var references + an external secret operator that injects values into the pod environment (e.g. External Secrets Operator, Vault Agent Injector)
