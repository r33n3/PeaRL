# Changelog

All notable changes to PeaRL are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- AIUC-1 responsible AI compliance gate — cross-framework satisfaction mapping (OWASP LLM, NIST RMF, MITRE ATLAS, SLSA, SSDF) with `pearl_get_aiuc_compliance` MCP tool
- Factory run summaries — per-WTK-session aggregated governance record with `pearl_get_run_summary` MCP tool
- `factory_run_summary_present` and `aiuc_compliance_score` gate rules for pilot→dev promotion
- Streamable HTTP MCP transport (`/mcp`) using the MCP Python SDK — replaces stdio-only server for LiteLLM integration
- `POST /auth/service-token` — 30-day JWT for machine-to-machine MCP callers
- AIUC-1 mandatory control list (28 controls) with per-control action hints in gate failure messages

### Fixed
- Gate rule sync was overwriting user customizations on every startup — now additive-only
- `pilot` environment missing from `Environment` enum causing 422 on env profile submission
- `promotions.py` fallback environment was `"sandbox"` (incorrect terminal env) — changed to `"pilot"`
- Path injection in scanning service — inputs validated via `_validate_scan_path`
- httpx clients now shared across adapter instances to prevent file descriptor exhaustion

---

## [1.1.0] — 2026-04-01

### Added
- **Workload Registry** — SPIRE SVID → task packet mapping with SSE events; `pearl_register_workload`, `pearl_deregister_workload` MCP tools
- **Agent Allowance Profiles** — 3-layer enforcement (org baseline → project → agent) with `pearl_allowance_check` MCP tool
- **Trust accumulation** — gates automatically pass after N consecutive clean evaluations (`trust_threshold` per gate)
- **Behavioral drift signals** — monitoring signals feed into gate evaluation; `drift_acute` findings block AIUC-1 controls
- **MASS 2.0 integration** — `MassClient` bridge, `mass_scan` worker, `mcp__mass__*` tool proxying
- **Snyk SCA ingest** — `POST /findings/ingest` accepts Snyk JSON; findings mapped to gate rules
- **Execution phase primitive** — task packets track `execution_phase` (planning → executing → complete) with phase history
- **Non-Human Identity (NHI) gate rules** — `nhi_identity_registered`, `nhi_secrets_in_vault`, `nhi_credential_rotation_policy`, `nhi_least_privilege_verified`, `nhi_token_expiry_configured`
- **Agent operational governance rules** — `agent_capability_scope_documented`, `agent_kill_switch_implemented`, `agent_blast_radius_assessed`, `agent_communication_secured`
- **OWASP LLM Top 10 gate rules** — discrete rules for LLM06, LLM07, LLM08, LLM10, LLM05
- **SBOM gate rule** — `sbom_generated` requires signed software bill of materials
- **Guardrails tab** — source badge for scanner-identified policies in the frontend
- LiteLLM compliance gate — checks proxy is configured and model restrictions enforced
- `pearl_get_run_summary`, `pearl_register_agent_for_stage`, `pearl_get_aiuc_compliance` MCP tools
- Attack chain security test suite (L2/L4/L5) — audit trail integrity, HMAC verification, spoofing prevention

### Changed
- Gate seed logic: additive-only — new rules are appended, existing customizations preserved
- Default promotion pipeline: `pilot → dev → prod` (removed sandbox as terminal env)
- `_build_eval_context` reads `EnvironmentProfileRow` when `ProjectRow.current_environment` is NULL

### Fixed
- Webhook idempotency — duplicate delivery no longer creates duplicate findings
- MCP audit events written via HTTP (not direct DB) — MCPServer has no DB session
- `PEARL_LOCAL=1` vs `settings.local_mode` distinction enforced in tests
- Silent gate re-evaluation failure in manual mode now raises instead of swallowing exception
- Shared httpx.AsyncClient in MCP server, MASS bridge, and integration adapters

---

## [1.0.0] — 2026-02-25

### Added
- **Core governance engine** — projects, org baselines, app specs, environment profiles, compiled context packages
- **Promotion gates** — configurable rule sets per environment transition; `evaluate`, `request`, `approve`, `rollback`
- **Findings pipeline** — ingest, normalize, quarantine, remediation specs, exceptions
- **Approval workflows** — `pending → approved/rejected/needs_info`; reviewer role enforcement
- **Task packets** — scoped work units with allowed/blocked actions, approval triggers, context budgets
- **Job queue** — Redis-backed async workers: `compile_context`, `normalize_findings`, `generate_remediation_spec`, `report`
- **MCP server** — 56 tools exposing all PeaRL operations to AI agents via stdio and streamable HTTP
- **Auth** — JWT (HS256 local, RS256 prod) + API key; roles: `viewer`, `operator`, `admin`, `service_account`
- **Multi-tenancy** — org isolation, org baselines, org-scoped gate defaults
- **SSE** — `GET /stream/events` real-time gate evaluation and finding ingest events
- **Observability** — structlog JSON, Prometheus metrics at `/metrics`, distributed trace IDs
- **React frontend** — gate editor, approval queue, findings dashboard, promotion flow, guardrails tab
- **Production deployment** — Kubernetes manifests, Docker Compose prod config, Nginx with TLS + SSE
- **CI/CD** — GitHub Actions: lint, test (PostgreSQL + Redis), release (GHCR + GitHub Release)
- **Policy versioning** — full audit trail of gate rule changes with `PolicyVersionRow`
- **Scan scheduler** — periodic scan target polling with Redis distributed lock

[Unreleased]: https://github.com/r33n3/PeaRL/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/r33n3/PeaRL/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/r33n3/PeaRL/releases/tag/v1.0.0
