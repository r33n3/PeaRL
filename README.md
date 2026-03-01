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
- **Frontend** (`frontend/`) — React + TypeScript dashboard (10 pages)
- **Security Controls** — 7-level autonomous agent attack chain blocked in production

---

## Quickstart (Local Dev)

### Prerequisites
- Python 3.12+
- Node 20+ (frontend only)
- Docker + Docker Compose

### 1. Clone and install

```bash
git clone https://github.com/your-org/pearl
cd pearl
pip install -e ".[dev]"
```

### 2. Start services (optional — local mode uses SQLite)

```bash
docker compose up -d postgres redis minio
```

### 3. Run the API in local mode

```bash
PEARL_LOCAL=1 uvicorn pearl.main:app --reload --port 8081
```

Or use Docker Compose for the full stack:

```bash
docker compose up
```

### 4. Run the frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open http://localhost:5173

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

# E2E (requires running server on port 8081)
cd e2e && npx playwright test
```

---

## MCP Integration

PeaRL exposes **39 tools** via MCP. Add to your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "pearl": {
      "command": "python3",
      "args": ["-m", "pearl_dev.unified_mcp", "--directory", ".", "--api-url", "http://localhost:8081/api/v1"],
      "env": {"PYTHONPATH": "/path/to/PeaRL/src"}
    }
  }
}
```

Or use the onboarding endpoint to auto-generate this file:

```bash
curl http://localhost:8081/api/v1/onboarding/setup | jq -r .bat_file > "Claude Code.bat"
```

The returned batch file handles WSL path conversion, `.mcp.json` generation, and auto-registration on launch.

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
