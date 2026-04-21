# PeaRL — Policy-Enforced Autonomous Risk Layer

**v1.1.0** | Model-free governance control plane for AI agent deployments.

---

## What PeaRL Is

PeaRL is a deterministic, model-free control plane that enforces governance over AI agent teams. It manages promotion gates, approval workflows, allowance profiles, workload registration, and audit controls — without making model calls. Every gate evaluation, trust verdict lookup, and allowance check is deterministic computation. This is a design property, not a limitation: it makes PeaRL auditable in a way that a model-based control plane cannot be.

Final authority on all governance decisions belongs to human reviewers. Agents that attempt to approve or decide their own requests receive a 403. Gates route decisions to humans — routing around a gate is never the correct response.

PeaRL supports two deployment tracks that reflect where the industry is today and where it is going.

---

## Two Deployment Tracks

### Secure Agent Factories (today)

Agent teams operate under human governance at defined checkpoints. Agents call PeaRL via LiteLLM MCP tools, execute tasks within their allowance profiles, and trigger gate evaluations at stage transitions. Human reviewers approve or reject gate decisions. This is the current production model.

### Secure Dark Agent Factories (aspirational)

Fully autonomous lights-out factories where no human is present in the loop for routine operations. PeaRL provides the kill switches, governance bounds, allowance profiles, and behavioral drift detection that make such a factory possible. Agents still receive 403 on decide endpoints. Kill switches and rollback authority remain with humans. This track is a design target, not a current deployment mode.

See [`docs/dark-factory-governance.md`](docs/dark-factory-governance.md) for the dark factory architecture and governance model.

---

## Architecture

```
  AI Agents                    PeaRL (governance plane)              Data
  (Claude Code,                ┌──────────────────────────────┐
   deepagents,   ─── LiteLLM ─▶│  FastAPI + SQLAlchemy async   │──▶  PostgreSQL
   custom runners)  MCP proxy  │  55 MCP governance tools      │──▶  Redis
                               │  JWT / API key auth (RBAC)    │──▶  MinIO / S3
  Human Reviewers ────────────▶│  Allowance profiles (3-layer) │
  (final authority)            │  Promotion gates              │
                               │  Workload registry            │      MASS 2.0
                               │  Behavioral drift signals     │──▶  (trust plane)
  Dashboard                    │  Factory run summaries        │◀──  (verdicts)
  (React + TypeScript) ───────▶│  Server-authoritative audit   │
                               └──────────────────────────────┘
                                  model-free · deterministic · auditable

  Background Workers (model-free only)
  ┌────────────────────────────────────────────────────────┐
  │  compile_context · scan_source · normalize_findings    │
  │  generate_remediation_spec · report · mass_scan        │
  └────────────────────────────────────────────────────────┘
```

**Key components:**

- **API** (`src/pearl/`) — FastAPI service with JWT/API key auth, RBAC, reviewer-gated governance endpoints
- **Workers** — deterministic background jobs only. No model calls.
- **MCP Server** — 55 PeaRL governance tools exposed via LiteLLM proxy (tool prefix: `PeaRL-pearl_*`)
- **Frontend** (`frontend/`) — React + TypeScript dashboard
- **Allowance Profiles** — 3-layer pre-tool enforcement: baseline, environment tier, task packet
- **Promotion Gates** — evidence-based gate rules with trust accumulation and behavioral drift detection
- **Workload Registry** — active agent instance tracking via SPIRE SVID
- **Factory Run Summaries** — aggregated per-run telemetry materialized at workload deregister
- **Trust Verdict Store** — MASS 2.0 artifacts, queryable by project, environment, and freshness
- **Audit Trail** — server-authoritative HMAC-signed records, immutable

---

## What PeaRL Does

- Enforces promotion gates between pipeline stages (`pilot → dev → prod`) with configurable gate rules
- Runs pre-tool allowance checks against 3-layer agent profiles in under 50ms
- Tracks active agent workloads (register, heartbeat, deregister) and materializes factory run summaries
- Ingests MASS 2.0 trust verdicts and gates promotions on verdict freshness and acceptability
- Accumulates trust scores across promotion gate evaluations
- Routes gate decisions to human reviewers via approval workflow; agents receive 403 on decide endpoints
- Enforces OWASP LLM Top 10, NHI (5 rules), Agent Governance (4 rules), and Supply Chain gate rules
- Provides a server-authoritative, HMAC-signed audit trail with no update or delete endpoints
- Streams real-time governance events via SSE
- Exposes all governance operations as MCP tools via LiteLLM proxy

---

## Quickstart

**Prerequisites:** Docker Desktop with WSL 2 integration enabled.

```bash
git clone https://github.com/r33n3/PeaRL
cd PeaRL
cp .env.example .env
docker compose up --build
```

| Service | URL |
|---|---|
| Dashboard | http://localhost:5177 |
| API | http://localhost:8080/api/v1 |
| Health | http://localhost:8080/api/v1/health/ready |
| MinIO console | http://localhost:9001 |

**Bootstrap credentials**

| | |
|---|---|
| Admin email | `admin@pearl.dev` |
| Admin password | `PeaRL-admin-2026` |
| Admin API key | `pearl-KYQXqnybaMaul7PoKJLsT4PZpZSFj0FIaVE2IPrQJNk` |
| Demo project | `proj_myapp001` |

The bootstrap admin account is seeded on first startup with all four roles: `admin`, `reviewer`, `operator`, `viewer`.

---

## Key Concepts

**Promotion Gate** — a configurable evaluation checkpoint between pipeline stages. A gate collects evidence (findings, trust verdicts, test results), evaluates configured rules, and either passes, blocks, or routes to a human reviewer. Gate decisions are deterministic and logged.

**Agent Allowance Profile** — a 3-layer policy (baseline, environment tier, task packet) that constrains what an agent may do before any tool call executes. Enforced by `pearl_allowance_check`. Layers compose: a task packet extension cannot exceed the environment tier ceiling.

**Workload Registry** — a live registry of active agent instances, each identified by a SPIRE SVID bound to a task packet. Agents register on start, send heartbeats, and deregister on exit.

**Factory Run Summary** — aggregated telemetry for a completed agent run: cost, tool calls, findings, gate outcomes. Materialized when the workload deregisters. Queryable per project, stage, and time range.

**Trust Accumulation** — each successful promotion gate evaluation increments a trust score for the project-stage pair. The score is factored into subsequent gate evaluations as evidence of sustained compliance.

---

## MCP Integration

Agents connect to PeaRL via a LiteLLM MCP proxy. All 55 governance tools are exposed under the prefix `PeaRL-pearl_*`.

Example tool names: `PeaRL-pearl_allowance_check`, `PeaRL-pearl_request_approval`, `PeaRL-pearl_evaluate_promotion`, `PeaRL-pearl_register_agent_for_stage`.

To wire an agent manually, point its MCP config at the LiteLLM proxy that has PeaRL registered as a tool server. The proxy handles authentication and tool routing.

See [`docs/integrations/litellm-mcp-adapter.md`](docs/integrations/litellm-mcp-adapter.md) for configuration details, tool listing, and example payloads.

---

## Agent Lifecycle

Agents register for a stage, receive a task packet, execute within their allowance profile, report findings, and trigger gate evaluation at completion. See [`docs/agent-lifecycle.md`](docs/agent-lifecycle.md) for the full lifecycle, state machine, and phase transition rules.

---

## Documentation

| Document | Description |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Full system architecture and data flows |
| [`docs/agent-lifecycle.md`](docs/agent-lifecycle.md) | Agent lifecycle, phases, and gate transitions |
| [`docs/dark-factory-governance.md`](docs/dark-factory-governance.md) | Dark factory architecture and governance model |
| [`docs/integrations/litellm-mcp-adapter.md`](docs/integrations/litellm-mcp-adapter.md) | LiteLLM MCP adapter configuration and tool reference |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | Development workflow and conventions |
| [`CLAUDE.md`](CLAUDE.md) | AI agent constraints enforced by the platform |

---

## Hard Constraints

These are enforced in code, not just documented here.

- **PeaRL never makes model calls.** Workers perform deterministic computation only. Adding a model call to a worker violates the core architectural constraint.
- **No self-approval.** Agents receive 403 on all `decide` and `createException` endpoints. This is correct behavior, not an error state.
- **Gates route to humans.** When a gate blocks an action, the correct response is to call `pearl_request_approval`, inform the user, and stop. Routing around a gate is never correct.
- **`PEARL_LOCAL=1` is a test harness flag.** It grants operator role and disables auth. Agents must never set or assume this flag in staging or production.
- **Audit records are immutable.** There are no update or delete endpoints on audit records.
- **Trust adjudication belongs to MASS 2.0.** PeaRL stores and presents verdicts; it does not generate them.

---

## Running Tests

```bash
# All tests (SQLite in-memory, no external services required)
PEARL_LOCAL=1 pytest tests/ -q

# With coverage
PEARL_LOCAL=1 pytest tests/ --cov=src/pearl --cov-report=term-missing

# Lint
ruff check src/ tests/
```

---

## License

MIT
