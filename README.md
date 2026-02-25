# PeaRL — Policy-enforced Autonomous Risk Layer

**v1.1.0** | API-first risk orchestration platform for autonomous coding and secure/responsible delivery.

PeaRL sits between your AI agents and production, enforcing governance gates, approval workflows, and security policies before any code change reaches users.

---

## Architecture

```
┌─────────────┐    ┌──────────────┐    ┌──────────────┐
│  AI Agents  │───▶│  PeaRL API   │───▶│  PostgreSQL   │
│  (MCP/SDK)  │    │  (FastAPI)   │    │  + Redis      │
└─────────────┘    └──────┬───────┘    └──────────────┘
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        ┌──────────┐ ┌────────┐ ┌─────────┐
        │ Scanners │ │ MinIO  │ │ Workers │
        │Snyk/Semgr│ │ (S3)   │ │(Queue)  │
        └──────────┘ └────────┘ └─────────┘
```

**Key components:**
- **API** (`src/pearl/`) — FastAPI REST service with JWT/API key auth, RBAC
- **Workers** — async background jobs: scan, normalize, remediate, report
- **Scheduler** — polls scan targets and enqueues periodic scans
- **MCP Server** — exposes PeaRL as tools for Claude and other AI agents
- **Frontend** (`frontend/`) — React + TypeScript dashboard

---

## Quickstart (Local Dev)

### Prerequisites
- Python 3.12+
- Node 20+ (frontend)
- Docker + Docker Compose

### 1. Clone and install

```bash
git clone https://github.com/your-org/pearl
cd pearl
pip install -e ".[dev]"
```

### 2. Start services

```bash
docker compose up -d postgres redis minio
```

### 3. Run the API in local mode (SQLite, no Alembic)

```bash
PEARL_LOCAL=1 uvicorn pearl.main:app --reload --port 8080
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

All settings are controlled by environment variables with the `PEARL_` prefix.

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

Key variables:

| Variable | Default | Description |
|---|---|---|
| `PEARL_LOCAL` | `0` | Set to `1` to use SQLite (no Postgres needed) |
| `PEARL_DATABASE_URL` | postgres://... | PostgreSQL connection string |
| `PEARL_JWT_SECRET` | dev-secret | JWT signing secret (change in prod!) |
| `PEARL_JWT_ALGORITHM` | `HS256` | `RS256` for production |
| `PEARL_CORS_ALLOWED_ORIGINS` | localhost origins | Comma-separated allowed origins |

---

## API Endpoints

All endpoints are under `/api/v1`. Interactive docs at http://localhost:8080/docs.

### Core
| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service health |
| `GET` | `/health/ready` | Readiness probe (DB + Redis check) |
| `GET` | `/health/live` | Liveness probe |
| `GET` | `/metrics` | Prometheus metrics |

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
| `POST` | `/projects/{id}/compile` | Compile context package |
| `POST` | `/projects/{id}/task-packets` | Generate task packet for agent |
| `POST` | `/task-packets/{id}/claim` | Agent claims packet |
| `POST` | `/task-packets/{id}/complete` | Agent reports outcome |
| `POST` | `/projects/{id}/promotions/evaluate` | Evaluate promotion readiness |
| `POST` | `/projects/{id}/promotions/rollback` | Rollback promotion (admin) |

### Real-time
| Method | Path | Description |
|---|---|---|
| `GET` | `/stream/events` | SSE stream for real-time events |

---

## Running Tests

```bash
# All tests (local mode)
PEARL_LOCAL=1 pytest tests/ -v

# With coverage
PEARL_LOCAL=1 pytest tests/ --cov=src/pearl --cov-report=term-missing

# Lint
ruff check src/ tests/
```

---

## Production Deployment

### Docker Compose (production)

```bash
docker compose -f docker-compose.yaml -f deploy/docker-compose.prod.yaml up -d
```

### Kubernetes

```bash
# Apply manifests
kubectl apply -f deploy/k8s/configmap.yaml
kubectl apply -f deploy/k8s/secret.yaml  # Edit with real values first!
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml
kubectl apply -f deploy/k8s/hpa.yaml
```

---

## MCP Integration

PeaRL exposes 40+ tools via MCP for AI agent integration:

```bash
# Start MCP server
pearl-mcp --directory /path/to/your/project --api-url http://localhost:8080/api/v1
```

Add to `.mcp.json`:
```json
{
  "mcpServers": {
    "pearl": {
      "command": "pearl-mcp",
      "args": ["--directory", "${workspaceFolder}"]
    }
  }
}
```

---

## License

MIT
