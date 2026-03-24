# SonarQube Integration

PeaRL pulls SAST and code-quality findings from SonarQube and normalizes them into the PeaRL finding model.
Gate rules can block promotions based on unresolved critical/high findings detected by SonarQube.

**No server restart required** — tokens are read from the database (or environment) at each connection attempt, so you can add or rotate credentials at any time from the admin panel.

---

## Prerequisites

- SonarQube Community, Developer, or Enterprise edition (8.x or later)
- A SonarQube **User Token** or **Project Token** with `Browse` permission on the target project(s)
- Network reachability between the PeaRL server and the SonarQube instance

---

## Step 1 — Generate a SonarQube Token

1. Log into your SonarQube instance
2. Click your avatar (top-right) → **My Account**
3. Select the **Security** tab
4. Under **Generate Tokens**:
   - **Name**: `pearl-scan-reader` (or similar)
   - **Type**: Choose based on scope:
     - **User Token** — can read all projects your user account has access to
     - **Project Token** — scoped to a single project (recommended for least-privilege)
     - **Global Analysis Token** — only needed if PeaRL also triggers analysis runs (not needed for pull-only)
   - **Expires in**: Set an expiry appropriate for your security policy
5. Click **Generate** and copy the token — it is shown only once

> **SonarQube token format:** Tokens generated in SonarQube 9.8+ start with `squ_`. Older tokens are plain alphanumeric strings. Both formats work with PeaRL.

---

## Step 2 — Add the Integration in PeaRL

No environment variable setup or server restart needed.

1. Open PeaRL → **Settings → Integrations**
2. Under **Security Scanning**, click the **+** button and select **SonarQube**
3. Fill in the form:

   | Field | What to enter | Example |
   |-------|---------------|---------|
   | **Base URL** | URL of your SonarQube server — no trailing slash | `http://localhost:9000` |
   | **API Token** | Paste your token directly — stored in PeaRL DB | `squ_xxxxxxxxxxxx` |
   | **Token Env Var (prod)** | *(optional)* Server env var name — overrides API Token if both are set | `SONARQUBE_TOKEN` |

4. Click **Save**

> **Local vs Production:**
> - **API Token field** — simplest for local development. Token is stored in the PeaRL database. No env var needed, no restart needed.
> - **Token Env Var field** — recommended for production. The secret stays out of the database. Set the env var on the server, enter only its name here (e.g. `SONARQUBE_TOKEN`).
> - If both are filled, the env var takes precedence at runtime.

---

## Step 3 — Test the Connection

Click the **Test** button on the SonarQube card.
PeaRL calls `GET /api/system/status` on your SonarQube instance using the configured token.
A green **Connected** badge confirms the integration is working.

**Common failures:**

| Error | Cause | Fix |
|-------|-------|-----|
| Connection failed | Wrong Base URL or SonarQube not reachable | Verify URL — should be `http://host:port`, not an email or username |
| HTTP 401 | Token missing, wrong, or expired | Re-paste the token in the API Token field |
| HTTP 403 | Token lacks Browse permission | Re-generate token with correct scope in SonarQube |
| Stored config is invalid | Old integration row with invalid field format | Delete and re-add the integration |

---

## Step 4 — Pull Findings

After the connection test passes, trigger a manual pull or wait for the scheduled scan (runs every 60 s by default).

**Manual pull via API:**
```bash
curl -X POST http://localhost:8081/api/v1/projects/{project_id}/integrations/{endpoint_id}/pull \
  -H "Authorization: Bearer $PEARL_TOKEN"
```

**Response:**
```json
{
  "endpoint_id": "intg_...",
  "endpoint_name": "SonarQube",
  "findings_pulled": 42,
  "synced_at": "2026-03-20T10:00:00+00:00"
}
```

---

## Optional — Restrict to Specific Projects

By default PeaRL pulls from all SonarQube projects accessible to the token.
To restrict to specific projects, add a `project_keys` label via the API when creating the integration:

```bash
curl -X POST http://localhost:8081/api/v1/integrations \
  -H "Authorization: Bearer $PEARL_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "SonarQube",
    "adapter_type": "sonarqube",
    "integration_type": "source",
    "category": "security_scanning",
    "base_url": "http://localhost:9000",
    "auth_config": { "auth_type": "bearer", "raw_token": "squ_..." },
    "labels": { "project_keys": "my-app,auth-service" }
  }'
```

Comma-separate multiple SonarQube project keys.

---

## Token Rotation

No server restart required.

1. Generate a new token in SonarQube (Step 1 above)
2. In PeaRL → **Settings → Integrations** → click **Edit** on the SonarQube card
3. Paste the new token in the **API Token** field and click **Save**
4. Click **Test** to confirm the new token works
5. Revoke the old token in SonarQube

---

## Severity Mapping

| SonarQube | PeaRL severity |
|-----------|---------------|
| BLOCKER   | critical |
| CRITICAL  | high |
| MAJOR     | moderate |
| MINOR     | low |
| INFO      | low |

---

## Issue Type Mapping

| SonarQube type | PeaRL source_type |
|----------------|------------------|
| VULNERABILITY  | sast |
| SECURITY_HOTSPOT | sast |
| BUG | sast |
| CODE_SMELL | sast |

---

## Production Env Var Setup (optional)

If you prefer to keep the token out of the database entirely:

**Bare metal / systemd:**
```bash
export SONARQUBE_TOKEN=squ_xxxxxxxxxxxx
# Then start PeaRL — token is read at connection time, not startup
```

**Docker / docker-compose:**
```yaml
# .env file (not committed)
SONARQUBE_TOKEN=squ_xxxxxxxxxxxx

# docker-compose.yml
services:
  pearl:
    env_file: .env
```

**Kubernetes:**
```bash
kubectl create secret generic pearl-secrets \
  --from-literal=SONARQUBE_TOKEN=squ_xxxxxxxxxxxx
```
```yaml
# deployment.yaml
envFrom:
  - secretRef:
      name: pearl-secrets
```

When using env var mode, enter only the variable **name** (e.g. `SONARQUBE_TOKEN`) in the **Token Env Var (prod)** field — not the token value itself.
Token rotation via env var: update the secret/env and roll the deployment pod; no PeaRL config change needed.
