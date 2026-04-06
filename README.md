# PeaRL — Model-Free Governance Platform for the Secure Agent Dark Factory

**v1.1.0** | The deterministic, human-in-the-loop control plane for AI agent promotion, autonomy elevation, and deployment governance.

PeaRL is the governance authority of the Secure Agent Dark Factory. It enforces promotion gates, approval workflows, allowance profiles, and audit controls over AI agents — without making model calls. Trust adjudication belongs to MASS 2.0. Final authority belongs to human reviewers. PeaRL owns everything in between.

---

## What PeaRL Does

```
Secure Agent Dark Factory
─────────────────────────────────────────────────────────────────────

  AI Agents            PeaRL (governance plane)       MASS 2.0
  (Claude Code,   ──▶  ┌──────────────────────────┐   (trust plane)
   deepagents,         │  Allowance profiles        │
   custom runners)     │  Execution phase tracking  │ ──▶ Trust review
                       │  Promotion gates           │     requests
  Human Reviewers ──▶  │  Approval workflows        │ ◀── Trust verdicts
  (final authority)    │  Workload registry         │
                       │  Behavioral drift signals  │
                       │  Server-authoritative audit│
                       └──────────────────────────┘
                              model-free · deterministic · auditable
```

**PeaRL never makes model calls.** Every gate check, approval decision, and promotion evaluation is deterministic. This is the design — it makes PeaRL auditable in a way that a model-based control plane cannot be.

---

## Architecture

```
┌─────────────────┐    ┌──────────────────────┐    ┌──────────────┐
│  AI Agents      │───▶│  PeaRL API (FastAPI)  │───▶│  PostgreSQL  │
│  (MCP / SDK)    │    │  50 MCP tools         │    │  + Redis     │
└─────────────────┘    │  JWT / API key auth   │    └──────────────┘
                       │  RBAC + reviewer gates│
┌─────────────────┐    │  Allowance profiles   │    ┌──────────────┐
│  Dashboard      │───▶│  Promotion gates      │───▶│  MinIO / S3  │
│  (React)        │    │  Trust verdict store  │    │  (reports)   │
└─────────────────┘    └──────────┬────────────┘    └──────────────┘
                                  │
                       ┌──────────▼────────────┐
                       │  Background Workers    │
                       │  (model-free only)     │
                       └───────────────────────┘
```

**Key components:**
- **API** (`src/pearl/`) — FastAPI service with JWT/API key auth, RBAC, reviewer-gated governance endpoints
- **Workers** — deterministic background jobs: compile context, scan, normalize findings, remediation spec, report. No model calls.
- **MCP Server** — 50 PeaRL governance tools for Claude Code and other AI agents
- **Frontend** (`frontend/`) — React + TypeScript dashboard (14 pages)
- **Allowance Profiles** — 3-layer pre-tool enforcement (baseline → environment tier → task packet)
- **Promotion Gates** — evidence-based gate rules with trust accumulation and behavioral drift detection
- **Trust Verdict Store** — MASS 2.0 trust review artifacts, queryable by project/environment/freshness
- **Audit Trail** — server-authoritative HMAC-signed records, immutable

---

## Quickstart

### Prerequisites
- Docker Desktop with WSL 2 integration enabled (Settings → Resources → WSL Integration)
- Python 3.12+ and Node 20+ only needed for [local dev mode](#local-dev-mode-no-docker)

---

### Option A — Full stack (Docker Compose, recommended)

```bash
git clone https://github.com/your-org/pearl
cd pearl
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:5177 |
| API | http://localhost:8080/api/v1 |
| MinIO console | http://localhost:9001 |

**Bootstrap credentials**
- Login: `admin@pearl.dev` / `PeaRL-admin-2026`
- API key: `pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk`

The bootstrap admin user is seeded automatically on first startup. The admin account has all four roles: `admin`, `reviewer`, `operator`, `viewer`.

> **Note:** The Postgres volume starts empty. Create your first project via the dashboard or the [Your First Project](#your-first-project) flow below.

---

### Option B — Local dev mode (no Docker)

Uses SQLite in-memory — no external services needed.

```bash
pip install -e ".[dev]"

# Terminal 1: API
PEARL_LOCAL=1 uvicorn pearl.main:app --reload --port 8081

# Terminal 2: Frontend
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. Auth is bypassed (operator role). Use `PEARL_LOCAL_REVIEWER=1` to add reviewer role (human reviewers only — do not set on an agent's behalf).

---

## Your First Project

### 1. Register the project

Via the dashboard or curl:

```bash
curl -s -X POST http://localhost:8080/api/v1/projects \
  -H "Content-Type: application/json" \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" \
  -d '{
    "project_id": "proj_myapp001",
    "name": "My First Project",
    "owner_team": "Engineering",
    "business_criticality": "high",
    "external_exposure": "public",
    "ai_enabled": true,
    "schema_version": "1.1"
  }'
```

### 2. Download the launcher (Windows + WSL)

```bash
curl -s http://localhost:8080/api/v1/onboarding/setup | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['bat_file'])" \
  > "Claude Code.bat"
```

Save `Claude Code.bat` somewhere convenient. On each run it:
1. Opens a folder browser — select your project folder
2. Writes `.mcp.json` into that folder (wires PeaRL MCP into Claude Code)
3. If `.pearl.yaml` exists, silently auto-registers the project with PeaRL
4. If no `.pearl.yaml` yet, prompts first-session registration via MCP
5. Launches `claude` in that folder

### 3. Get the project config files

```bash
PROJECT=proj_myapp001
API=http://localhost:8080/api/v1
KEY="pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"

curl -s "$API/projects/$PROJECT/pearl.yaml" -H "X-API-Key: $KEY" > .pearl.yaml
curl -s "$API/projects/$PROJECT/mcp.json"  -H "X-API-Key: $KEY" > .mcp.json
```

- `.pearl.yaml` — project identity + branch→environment mapping (commit this)
- `.mcp.json` — MCP server config pointing Claude Code at PeaRL (gitignore or commit per team)

### 4. Open the project in Claude Code

Double-click `Claude Code.bat`, select your project folder. All 50 PeaRL MCP tools are available.

Key tools from the first prompt:
- `pearl_allowance_check` — pre-tool enforcement against agent allowance profile
- `pearl_get_project` — load project context and governance rules
- `pearl_submit_findings` — report security/compliance findings
- `pearl_request_approval` — gate a decision through a human reviewer
- `pearl_evaluate_promotion` — check if code is ready to promote to the next environment

### 5. Monitor on the dashboard

- **Projects** — gate status, promotion history, trust verdicts
- **Clearances** — pending approval requests from agents
- **Workloads** — live agent sessions registered via SPIRE SVID
- **Administration → Project Data** — delete projects during testing (admin only)

---

## Configuration

All settings use the `PEARL_` prefix. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
chmod 400 .env
```

| Variable | Default | Description |
|---|---|---|
| `PEARL_LOCAL` | `0` | `1` → SQLite, operator-only role, no migrations needed |
| `PEARL_LOCAL_REVIEWER` | `0` | `1` → adds reviewer role in local mode (human reviewers only) |
| `PEARL_DATABASE_URL` | postgres://... | PostgreSQL connection string |
| `PEARL_JWT_SECRET` | dev-secret | JWT signing secret (change in prod) |
| `PEARL_JWT_ALGORITHM` | `HS256` | `RS256` for production |
| `PEARL_CORS_ALLOWED_ORIGINS` | localhost origins | Comma-separated allowed origins |
| `PEARL_REDIS_URL` | redis://localhost:6379 | Redis connection |
| `PEARL_PORT` | `8081` | API server port |
| `PEARL_AUDIT_HMAC_KEY` | dev-hmac-key | HMAC key for audit record signing (change in prod) |
| `PEARL_API_KEY_HMAC_SECRET` | — | HMAC secret for API key hashing (falls back to JWT secret if unset) |

---

## API Endpoints

All endpoints at `/api/v1`. Docs at http://localhost:8081/docs (local mode only).

### Infrastructure
| Method | Path | Description |
|---|---|---|
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/health/ready` | Readiness probe (DB + Redis) |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/onboarding/setup` | Claude Code launcher + setup |

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Email + password → JWT |
| `POST` | `/auth/refresh` | Refresh token → new access token |
| `POST` | `/auth/logout` | Invalidate refresh token |
| `POST` | `/users` | Create user (admin only) |
| `GET` | `/users/me` | Current user profile |
| `POST` | `/users/me/api-keys` | Create API key |

**Canonical roles:**

| Role | Intent |
|---|---|
| `viewer` | Read-only access |
| `operator` | Submit work, ingest findings |
| `service_account` | Machine callers (scanners, CI) via API key |
| `reviewer` | Approve/reject gates and exceptions — human only |
| `admin` | User management, baseline config, bulk operations |

### Projects & Governance
| Method | Path | Description |
|---|---|---|
| `POST` | `/projects` | Register project |
| `GET` | `/projects/{id}/pearl.yaml` | Project governance config |
| `GET` | `/projects/{id}/mcp.json` | Pre-configured `.mcp.json` |
| `POST` | `/projects/{id}/compile` | Compile context package |
| `POST` | `/projects/{id}/task-packets` | Generate task packet |
| `POST` | `/task-packets/{id}/claim` | Agent claims packet |
| `POST` | `/task-packets/{id}/complete` | Agent reports outcome |
| `PATCH` | `/task-packets/{id}/phase` | Advance execution phase |
| `POST` | `/projects/{id}/promotions/evaluate` | Evaluate promotion readiness |
| `POST` | `/projects/{id}/promotions/request` | Request promotion |
| `POST` | `/projects/{id}/promotions/rollback` | Rollback (admin) |
| `POST` | `/approvals/{id}/decide` | Approve/reject (reviewer required) |
| `POST` | `/exceptions/{id}/decide` | Approve/reject exception (reviewer required) |

### Allowance Profiles
| Method | Path | Description |
|---|---|---|
| `POST` | `/allowance-profiles` | Create profile |
| `GET` | `/allowance-profiles/{id}` | Get profile |
| `POST` | `/allowance-profiles/{id}/check` | Pre-tool enforcement check (<50ms) |
| `GET` | `/task-packets/{id}/allowance` | Resolved 3-layer profile for task |

### Workloads
| Method | Path | Description |
|---|---|---|
| `POST` | `/workloads/register` | Register SPIRE SVID → task packet |
| `POST` | `/workloads/{svid}/heartbeat` | Agent heartbeat |
| `DELETE` | `/workloads/{svid}` | Deregister on exit |
| `GET` | `/workloads` | Active workload list |

### Trust Verdicts
| Method | Path | Description |
|---|---|---|
| `POST` | `/projects/{id}/trust-review/request` | Request MASS trust review |
| `POST` | `/projects/{id}/trust-review/ingest` | Ingest MASS trust verdict |
| `GET` | `/projects/{id}/trust-review/latest` | Latest verdict for project/environment |

### Telemetry
| Method | Path | Description |
|---|---|---|
| `POST` | `/projects/{id}/audit-events` | Ingest agent audit events (batch, max 500) |
| `POST` | `/projects/{id}/cost-entries` | Ingest agent cost ledger entries (batch, max 500) |

### Real-time
| Method | Path | Description |
|---|---|---|
| `GET` | `/stream/events` | SSE stream for real-time governance events |

---

## Running Tests

```bash
# All tests (local mode — SQLite, no external services)
PEARL_LOCAL=1 pytest tests/ -q

# With coverage
PEARL_LOCAL=1 pytest tests/ --cov=src/pearl --cov-report=term-missing

# Lint
ruff check src/ tests/
```

---

## MCP Integration

PeaRL exposes **50 tools** via MCP. The [Your First Project](#your-first-project) flow handles `.mcp.json` generation automatically.

To wire manually:

```json
{
  "mcpServers": {
    "pearl": {
      "command": "python3",
      "args": ["-m", "pearl_dev.unified_mcp", "--directory", ".", "--api-url", "http://localhost:8080/api/v1"],
      "env": {"PYTHONPATH": "/path/to/PeaRL/src"}
    }
  }
}
```

---

## Governance Model

### Hard constraints (enforced in code, not just docs)

- **Model-free workers** — no LLM calls inside PeaRL. Deterministic computation only.
- **Reviewer role required** for all approval and exception decisions — agents receive 403, this is correct behavior
- **No self-approval path** — the agent that creates a request cannot decide it
- **PEARL_LOCAL=1 is a test harness** — grants operator role only; never set by agents in staging or production
- **Audit trail is immutable** — no update/delete endpoints on audit records
- **Trust adjudication belongs to MASS 2.0** — PeaRL stores and presents verdicts; it does not generate them

### Promotion path

```
dev → pilot → preprod → prod
```

Each transition is gate-evaluated. `preprod → prod` requires a fresh MASS trust verdict. Auto-pass is blocked when a trust review is required but absent, stale, or unacceptable.

### Allowance profile layers

1. **Baseline** — per agent type: blocked commands, blocked paths, pre-approved actions, model restrictions, budget cap
2. **Environment tier** — permissive / standard / strict / locked
3. **Task packet** — per-sprint extensions: allowed paths, pre-approved commands

`pearl_allowance_check` enforces all three layers deterministically before every tool call.

---

## Attack Chain Defences

PeaRL was tested against autonomous agents attempting to self-approve governance exceptions via a 7-level attack chain:

- **L1** — MCP tool abuse: service account cannot self-approve (403 enforced)
- **L2** — Token escalation: refresh token replay after logout blocked
- **L3** — API auth bypass: middleware blocks all unauthenticated requests
- **L4** — Governance bypass: exception creation without reviewer approval blocked (403)
- **L5** — Audit spoofing: forged audit records detectable via HMAC mismatch

See [`docs/security_research/`](docs/security_research/) for full research and hardening guide.

---

## Production Deployment

### Docker Compose

```bash
docker compose -f docker-compose.yaml -f deploy/docker-compose.prod.yaml up -d
```

### Kubernetes

```bash
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.yaml    # Edit with real values first
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
kubectl apply -f deploy/k8s/hpa.yaml
```

See [`deploy/nginx/pearl.conf`](deploy/nginx/pearl.conf) for Nginx TLS + SSE configuration.

---

## Documentation

| Doc | Description |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Full system architecture and data flows |
| [`docs/adr/`](docs/adr/) | Architecture decision records |
| [`docs/security_research/`](docs/security_research/) | Attack chain research and hardening guide |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development workflow |
| [`CLAUDE.md`](CLAUDE.md) | AI agent constraints enforced by the platform |
| [`SPEC.md`](SPEC.md) | Feature status and acceptance criteria |

---

## License

MIT
