# PeaRL — Policy-enforced Autonomous Risk Layer

**v1.1.0** | API-first risk orchestration platform for autonomous coding and secure/responsible delivery.

PeaRL sits between your AI agents and production, enforcing governance gates, approval workflows, security policies, and fairness requirements before any AI-driven change reaches users.

---

## Architecture

```
┌─────────────┐    ┌──────────────────────┐    ┌──────────────┐
│  AI Agents  │───▶│  PeaRL API (FastAPI)  │───▶│  PostgreSQL   │
│  (MCP/SDK)  │    │  39 MCP tools         │    │  + Redis      │
└─────────────┘    │  33 route files        │    └──────────────┘
                   │  JWT/API key auth      │
┌─────────────┐    │  RBAC + reviewer gates │    ┌──────────────┐
│  Dashboard  │───▶│                        │───▶│  MinIO / S3  │
│  (React)    │    └──────────┬─────────────┘    │  (reports)   │
└─────────────┘               │                  └──────────────┘
                   ┌──────────▼─────────────┐
                   │  Background Workers     │
                   │  + Scan Scheduler       │
                   └─────────────────────────┘
```

**Key components:**
- **API** (`src/pearl/`) — FastAPI service with JWT/API key auth, RBAC, reviewer-gated governance endpoints
- **Workers** — async background jobs: compile context, scan, normalize, remediate, report
- **Scheduler** — polls scan targets and enqueues periodic scans (Redis distributed lock)
- **MCP Server** — exposes 39 PeaRL tools for Claude and other AI agents
- **Frontend** (`frontend/`) — React + TypeScript dashboard with JWT login (12 pages). Org baseline editing lives in **Policy**, not Configuration.
- **Security Controls** — 7-level autonomous agent attack chain blocked in production

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

The bootstrap admin user is seeded automatically on first startup. Navigate to the dashboard and sign in with the credentials above. The admin account has all four roles: `admin`, `reviewer`, `operator`, `viewer`.

> **Note:** The Postgres volume starts empty. You need to create your first project (see [Your First Project](#your-first-project) below).

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

Via the dashboard (http://localhost:5174) or curl:

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

The onboarding endpoint generates a Windows batch file that wires everything up automatically:

```bash
curl -s http://localhost:8080/api/v1/onboarding/setup | python3 -c \
  "import sys,json; print(json.load(sys.stdin)['bat_file'])" \
  > "Claude Code.bat"
```

Save `Claude Code.bat` somewhere convenient (e.g. `C:\Users\<you>\Development\`).

**What the launcher does on each run:**
1. Opens a folder browser — select your project folder
2. Writes `.mcp.json` into that folder if it doesn't already exist (wires PeaRL MCP into Claude Code)
3. If `.pearl.yaml` exists, silently auto-registers the project
4. If no `.pearl.yaml` yet, prints a first-prompt instruction to register via MCP
5. Launches `claude` in that folder

### 3. Get the project config files

After registering, download both governance config files into your project folder:

```bash
PROJECT=proj_myapp001
API=http://localhost:8080/api/v1
KEY="pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk"

curl -s "$API/projects/$PROJECT/pearl.yaml" -H "X-API-Key: $KEY" > .pearl.yaml
curl -s "$API/projects/$PROJECT/mcp.json"  -H "X-API-Key: $KEY" > .mcp.json
```

- `.pearl.yaml` — project identity + branch→environment mapping (commit this)
- `.mcp.json` — MCP server config pointing Claude Code at PeaRL (gitignore or commit depending on team setup)

### 4. Open the project in Claude Code

Double-click `Claude Code.bat`, select your project folder. Claude Code starts with all 39 PeaRL MCP tools available.

From the first prompt, Claude can:
- `pearl_get_project` — load project context and governance rules
- `pearl_submit_findings` — report security/compliance findings
- `pearl_request_approval` — gate a decision through a human reviewer
- `pearl_evaluate_promotion` — check if code is ready to promote to the next environment
- `pearl_compile_context` — build a full governance context package

### 5. Monitor on the dashboard

- **Projects** — overview of all projects and their gate status
- **Clearances** — pending approval requests from agents
- **Administration → Project Data** — delete projects during setup/testing (admin only)

---

## Configuration

All settings use the `PEARL_` prefix. Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
chmod 400 .env   # prevent accidental writes
```

| Variable | Default | Description |
|---|---|---|
| `PEARL_LOCAL` | `0` | `1` → SQLite, operator-only role, no migrations needed |
| `PEARL_LOCAL_REVIEWER` | `0` | `1` → adds reviewer role in local mode (for human reviewers only — do not set on agent's behalf) |
| `PEARL_DATABASE_URL` | postgres://... | PostgreSQL connection string |
| `PEARL_JWT_SECRET` | dev-secret | JWT signing secret (change in prod!) |
| `PEARL_JWT_ALGORITHM` | `HS256` | `RS256` for production |
| `PEARL_CORS_ALLOWED_ORIGINS` | localhost origins | Comma-separated allowed origins |
| `PEARL_EXPOSE_OPENAPI` | `1` in local, `0` in prod | Expose `/docs` and `/openapi.json` |
| `PEARL_REDIS_URL` | redis://localhost:6379 | Redis connection |
| `PEARL_PORT` | `8081` | API server port |

---

## API Endpoints

All endpoints at `/api/v1`. Docs at http://localhost:8081/docs (local mode only).

### Infrastructure
| Method | Path | Description |
|---|---|---|
| `GET` | `/health/live` | K8s liveness probe |
| `GET` | `/health/ready` | K8s readiness probe (checks DB + Redis) |
| `GET` | `/server-config` | Current reviewer/local mode flags (used by dashboard) |
| `GET` | `/metrics` | Prometheus metrics |
| `GET` | `/onboarding/setup` | Claude Code batch file + setup instructions |

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/login` | Email + password → JWT |
| `POST` | `/auth/refresh` | Refresh token → new access token |
| `POST` | `/auth/logout` | Invalidate refresh token |
| `POST` | `/users` | Create user (admin only) |
| `GET` | `/users/me` | Current user profile |
| `POST` | `/users/me/api-keys` | Create API key |

**Canonical roles** (set per user, multiple allowed):

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
| `GET` | `/projects/{id}/pearl.yaml` | Download project governance config |
| `GET` | `/projects/{id}/mcp.json` | Download pre-configured `.mcp.json` |
| `POST` | `/projects/{id}/compile` | Compile context package for agent |
| `POST` | `/projects/{id}/task-packets` | Generate remediation task packet |
| `POST` | `/task-packets/{id}/claim` | Agent claims packet |
| `POST` | `/task-packets/{id}/complete` | Agent reports outcome |
| `POST` | `/projects/{id}/promotions/evaluate` | Evaluate promotion readiness |
| `POST` | `/projects/{id}/promotions/request` | Request promotion |
| `POST` | `/projects/{id}/promotions/rollback` | Rollback promotion (admin) |
| `POST` | `/approvals/{id}/decide` | Approve/reject (reviewer role required) |
| `POST` | `/exceptions/{id}/decide` | Approve/reject exception (reviewer role required) |

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

# E2E (requires running API + frontend)
cd tests/e2e && npx playwright test
```

---

## MCP Integration

PeaRL exposes **39 tools** via MCP for Claude Code and other MCP-compatible AI agents.

The easiest path is the [Your First Project](#your-first-project) flow above — the launcher and config endpoints handle `.mcp.json` generation automatically.

To wire it manually, add to your project's `.mcp.json`:

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

Or fetch a pre-configured file for a specific project:

```bash
curl http://localhost:8080/api/v1/projects/{project_id}/mcp.json \
  -H "X-API-Key: pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk" > .mcp.json
```

---

## Autonomous Agent Security

PeaRL was red-team tested against an autonomous AI agent that attempted to self-approve governance exceptions via a 7-level attack chain. Hard controls are deployed:

- Reviewer role required for all governance decide endpoints — agents get 403
- `PEARL_LOCAL=1` grants only `operator` role; reviewer role requires `PEARL_LOCAL_REVIEWER=1` set manually by a human
- OpenAPI schema hidden in production (`PEARL_EXPOSE_OPENAPI=0`)
- `disallowedBashCommands` in `.mcp.json` for governance API endpoints
- `PreToolUse` Bash guard hook (`scripts/pearl_bash_guard.py`) blocks governance bypass patterns
- All 403 AuthorizationErrors emit structured `governance_access_denied` warning logs for SIEM alerting

See [`docs/security_research/pearl_autonomous_attack_research.md`](docs/security_research/pearl_autonomous_attack_research.md) for full research.
See [`docs/security_research/SECURITY_HARDENING.md`](docs/security_research/SECURITY_HARDENING.md) for operational hardening steps.

---

## Production Deployment

### Docker Compose (production)

```bash
docker compose -f docker-compose.yaml -f deploy/docker-compose.prod.yaml up -d
```

### Kubernetes

```bash
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.yaml    # Edit with real values first!
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
| [`docs/architecture.md`](docs/architecture.md) | Full system architecture, data flows, security model |
| [`docs/security_research/pearl_autonomous_attack_research.md`](docs/security_research/pearl_autonomous_attack_research.md) | Autonomous agent attack chain research |
| [`docs/security_research/SECURITY_HARDENING.md`](docs/security_research/SECURITY_HARDENING.md) | Operational security hardening guide |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development workflow and contribution guidelines |
| [`CLAUDE.md`](CLAUDE.md) | AI agent governance constraints (enforced by the platform) |

---

## License

MIT
