# Platform-Agnostic Agent Governance Design

**Date:** 2026-04-12
**Status:** Approved
**Scope:** PeaRL refactor to govern Claude Managed Agents and OpenAI Agents platform deployments

---

## Problem

PeaRL currently gates code deployments via scan workers (ScanWorker, MassScanWorker, etc.) running against source code repos. The system being governed is shifting: agents defined as YAML/JSON in git, deployed to Claude Managed Agents or OpenAI Agents API, are the new deployment artifacts. Code scanning becomes relevant only for MCP servers and custom tools — not for agents themselves. MASS 2.0 is also moving to the Claude Managed Agents platform, eliminating the self-hosted Docker stack.

---

## Goals

1. PeaRL governs **agent deployments** (YAML/JSON definitions → platform) in addition to code
2. MASS 2.0 runs as a Managed Agent (Claude or OpenAI) — PeaRL creates sessions rather than calling a self-hosted HTTP endpoint
3. Platform choice (Claude vs OpenAI) is a **config decision**, not a code change
4. Existing gate, promotion, approval, findings, and MCP infrastructure stays intact

---

## Architecture

### Before

```
CI (code repo) → PeaRL scan workers → MASS (Docker) → /integrations/mass/ingest → gate
```

### After

```
CI (agent.yaml in git)
    ↓  POST /agent-definitions
PeaRL parses definition → AgentDefinitionRow (pending_assessment)
    ↓  BackgroundTask
adapter.create_session(MASS_AGENT_ID, task="Assess: <yaml>")
    ↓  runs on Claude or OpenAI platform
MASS session → calls PeaRL MCP tools → findings + scanner policies land in PeaRL
    ↓
AgentDefinitionRow.status = assessed
    ↓
Gate: agent_definition_assessed rule → promote dev→prod or block
```

### Platform selection (config-driven)

```python
MASS_PLATFORM = "claude"   # or "openai" — swap without code changes
MASS_AGENT_ID = "agt_01xxx"  # or "wf_xxx" for OpenAI
```

---

## What Gets Removed

| Removed | Replaced By |
|---|---|
| `src/pearl/scanning/mass_bridge.py` (MassClient) | `AgentAssessmentService` + adapter |
| `_enrich_from_mass` BackgroundTask | MASS pushes via PeaRL MCP tools during session |
| `POST /integrations/mass/ingest` | MCP tools (`pearl_ingest_finding` etc.) |
| `ScanWorker`, `SonarScanWorker`, `MassScanWorker` | Agent sessions (for AI assessment) |
| Redis job queue (scan jobs) | Significantly reduced — only non-agent workers remain |

Code scanning (Snyk, Semgrep, Trivy) is retained only for the MCP server / tool deployment pipeline.

---

## What Stays Unchanged

- Gate evaluator + promotion workflow
- Human approval workflow
- `scanner_policy_store` + `ScannerPolicyRepository` (populated by MASS via MCP)
- All 41 MCP tools — MASS Managed Agent has PeaRL MCP configured as tool provider
- Findings model + repositories
- Frontend (minimal additions only)
- Auth, RBAC, audit events

---

## Data Model

### New table: `agent_definitions` (migration 007)

| Column | Type | Notes |
|---|---|---|
| `agent_definition_id` | String(64) PK | prefix: `def_` |
| `project_id` | String(128) FK → projects | |
| `git_ref` | String(64) | commit SHA |
| `git_path` | String(256) | path to YAML/JSON in repo |
| `platform` | String(20) | `claude` \| `openai` |
| `platform_agent_id` | String(128) nullable | `agt_xxx` or `wf_xxx` — null until deployed |
| `definition` | JSON | full parsed YAML content |
| `capabilities` | JSON | extracted: `{tools, mcp_servers, model, callable_agents, skills, system_prompt_hash}` |
| `environment` | String(20) | `dev` \| `prod` |
| `status` | String(30) | `pending_assessment` \| `assessed` \| `approved` \| `rejected` |
| `version` | String(64) | git tag or SHA-derived |
| `created_at` | DateTime(tz) | |

Unique constraint: `(project_id, git_ref, git_path, environment)`

### New table: `agent_sessions` (migration 008)

| Column | Type | Notes |
|---|---|---|
| `agent_session_id` | String(64) PK | prefix: `ses_` |
| `definition_id` | String(64) FK → agent_definitions | |
| `project_id` | String(128) FK → projects | |
| `platform` | String(20) | `claude` \| `openai` |
| `platform_session_id` | String(128) | Claude session_id or OpenAI run_id |
| `purpose` | String(30) | `assessment` \| `execution` \| `remediation` |
| `status` | String(20) | `running` \| `completed` \| `failed` \| `interrupted` |
| `result` | JSON | `{verdict, findings_count, outcome_result}` |
| `cost_usd` | Float nullable | from session usage events |
| `started_at` | DateTime(tz) | |
| `completed_at` | DateTime(tz) nullable | |

### _EvalContext additions

```python
self.agent_definition_id: str | None = None
self.agent_definition_status: str | None = None  # "approved" | "rejected" | "pending_assessment"
```

Loaded from `AgentDefinitionRow` in `_build_eval_context` for the project's current environment.

---

## Adapter Interface

### `BaseAgentPlatformAdapter` (`integrations/adapters/base_agent.py`)

```python
class BaseAgentPlatformAdapter(ABC):

    @abstractmethod
    async def create_session(
        self,
        agent_id: str,
        task: str,
        environment_id: str | None = None,
    ) -> str: ...                        # returns platform_session_id

    @abstractmethod
    async def get_result(
        self,
        session_id: str,
    ) -> AgentSessionResult: ...

    @abstractmethod
    async def stream_events(
        self,
        session_id: str,
    ) -> AsyncIterator[AgentSessionEvent]: ...

    @abstractmethod
    async def interrupt(self, session_id: str) -> None: ...
```

### Common result types

```python
@dataclass
class AgentSessionResult:
    status: str           # completed | failed | interrupted
    output: str | None    # final text output
    files: list[str]      # file IDs (Claude Files API) or attachment IDs
    cost_usd: float | None
    raw: dict

@dataclass
class AgentSessionEvent:
    type: str             # message | tool_call | tool_result | status_change
    content: str | None
    tool_name: str | None
    raw: dict
```

### Platform mapping

| Concept | Claude Managed Agents | OpenAI Agents API |
|---|---|---|
| `agent_id` | `agt_xxx` | `wf_xxx` (workflow ID) |
| `create_session` | `client.beta.sessions.create(agent=agent_id)` | create thread + run against workflow |
| `stream_events` | `client.beta.sessions.threads.stream(...)` | stream run events |
| `get_result` | retrieve session + outcome_evaluations | retrieve run + run steps |
| Task format | any string | `"Scan <context>"` (ChatKit convention) |

### `ClaudeManagedAgentsAdapter` (`integrations/adapters/claude_managed_agents.py`)

- Wraps `anthropic.Anthropic().beta.sessions`
- MASS session has PeaRL MCP URL in its agent config on platform.claude.com
- **PeaRL MCP server must be publicly reachable** (or via ngrok/tunnel in dev) for MASS to call it
- Findings arrive via MCP calls during session — no polling needed for findings
- `stream_events` maps SSE event types to `AgentSessionEvent`

### `OpenAIAgentsAdapter` (`integrations/adapters/openai_agents.py`)

- Wraps OpenAI SDK runs/threads against workflow ID
- Task string: `f"Assess agent definition:\n\n{yaml_content}"`
- Maps run steps to `AgentSessionEvent`
- Results retrieved from run output messages

### Adapter factory

```python
# integrations/adapters/__init__.py
def get_agent_platform_adapter(platform: str) -> BaseAgentPlatformAdapter:
    if platform == "claude":
        return ClaudeManagedAgentsAdapter(api_key=settings.anthropic_api_key)
    if platform == "openai":
        return OpenAIAgentsAdapter(api_key=settings.openai_api_key)
    raise ValueError(f"Unknown platform: {platform}")
```

---

## AgentAssessmentService

Replaces `MassClient`. Lives at `src/pearl/services/agent_assessment.py`.

```python
class AgentAssessmentService:
    def __init__(self, adapter: BaseAgentPlatformAdapter, session: AsyncSession): ...

    async def assess_definition(
        self,
        project_id: str,
        definition_id: str,
        definition_yaml: str,
    ) -> str:
        # 1. Build task string
        # 2. adapter.create_session(settings.mass_agent_id, task)
        # 3. Create AgentSessionRow (purpose=assessment, status=running)
        # 4. Return platform_session_id
        # Findings arrive via MCP during session — no polling needed for findings
        # AgentSessionRow.status updated by a scheduler polling platform API every 30s
        # (same pattern as existing ScanWorker) until session status = completed/failed
```

---

## New API Endpoint

### `POST /projects/{project_id}/agent-definitions`

**Request:**
```json
{
  "git_ref": "a3f9c21",
  "git_path": "agents/orchestrator/agent.yaml",
  "platform": "claude",
  "platform_agent_id": "agt_01xxx",
  "definition": "<raw YAML or JSON string>"
}
```

**Behavior:**
1. Parse definition → extract capabilities
2. Create `AgentDefinitionRow` (`status: pending_assessment`)
3. Fire `AgentAssessmentService.assess_definition()` as BackgroundTask
4. Return `{"definition_id": "def_xxx", "status": "pending_assessment"}`

**Auth:** requires `operator` role or `service_account`

---

## New Gate Rule: `agent_definition_assessed`

```python
def _eval_agent_definition_assessed(rule, ctx):
    if ctx.agent_definition_id is None:
        return True, "No agent definition — non-agent project", {}
    if ctx.agent_definition_status == "approved":
        return True, f"Agent definition {ctx.agent_definition_id} approved", {}
    if ctx.agent_definition_status == "rejected":
        return False, f"Agent definition {ctx.agent_definition_id} rejected by MASS assessment", {}
    return False, f"Agent definition {ctx.agent_definition_id} pending assessment", {}
```

Added to `gate_evaluator.py` rule dispatch alongside existing rules.

---

## Settings Additions

```
ANTHROPIC_API_KEY       str     Claude API key (Managed Agents)
OPENAI_API_KEY          str     OpenAI API key (Agents API)
MASS_PLATFORM           str     "claude" | "openai"  default: "claude"
MASS_AGENT_ID           str     agt_xxx (Claude) or wf_xxx (OpenAI)
MASS_ENVIRONMENT_ID     str     Claude environment ID (unused for OpenAI)
```

---

## CI Integration

```yaml
# .github/workflows/agent-deploy.yml
- name: Register agent definition with PeaRL
  run: |
    curl -X POST $PEARL_URL/api/v1/projects/$PROJECT_ID/agent-definitions \
      -H "X-API-Key: $PEARL_API_KEY" \
      -H "Content-Type: application/json" \
      -d "{
        \"git_ref\": \"$GITHUB_SHA\",
        \"git_path\": \"agents/orchestrator/agent.yaml\",
        \"platform\": \"claude\",
        \"definition\": $(cat agents/orchestrator/agent.yaml | jq -Rs .)
      }"

- name: Wait for PeaRL gate
  run: pearl-cli gate-check --project $PROJECT_ID --env dev --timeout 300
```

---

## Migration Path

1. Implement migrations 007 + 008
2. Implement adapter interface + both platform adapters
3. Implement `AgentAssessmentService` (replaces `MassClient`)
4. Add `POST /agent-definitions` endpoint
5. Add `agent_definition_assessed` gate rule
6. Deprecate `mass_bridge.py`, `_enrich_from_mass`, `/integrations/mass/ingest`
7. Remove deprecated code after MASS is confirmed running on Managed Agents platform
8. Test: publish MASS orchestrator to Claude/OpenAI, register an agent definition, validate assessment → gate → promotion

---

## Out of Scope

- Frontend changes beyond showing `AgentDefinitionRow` status in project detail
- Full session event streaming UI (future)
- Multi-agent orchestration within PeaRL (PeaRL remains deterministic/model-free per CLAUDE.md)
- Cost optimization logic between platforms (config-driven swap is sufficient)
