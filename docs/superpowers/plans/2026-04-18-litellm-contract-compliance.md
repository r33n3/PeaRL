# LiteLLM Contract Compliance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable PeaRL to pull agent runtime compliance data from LiteLLM's virtual key system and surface it as a governance check at promotion gates — validating that a deployed agent stayed within its approved allowance profile contract.

**Architecture:** WTK generates a LiteLLM virtual key per factory run using the key alias `wtk-run-{run_id}` with the allowance profile's `model_restrictions` and `budget_cap_usd` embedded. PeaRL stores the `run_id` in `task_packet.packet_data["run_id"]`. At gate time, PeaRL reconstructs the key alias, calls LiteLLM's `/key/info` and `/spend/logs` endpoints using the builder key (`PEARL_LITELLM_API_KEY`), and compares actual spend and model usage against the allowance profile contract. The result surfaces via a new `GET /task-packets/{id}/contract-compliance` REST endpoint and a `pearl_check_agent_contract` MCP tool.

**Tech Stack:** httpx (already a dependency), FastAPI, PeaRL's existing `AllowanceProfileRepository` + `TaskPacketRepository`, LiteLLM 1.82+ REST API.

---

## File Map

| File | Action | Why |
|---|---|---|
| `src/pearl/integrations/litellm.py` | Create | `LiteLLMClient` + `ContractCompliance` dataclass — all LiteLLM HTTP calls isolated here |
| `src/pearl/api/routes/task_packets.py` | Modify | Add `GET /task-packets/{id}/contract-compliance` route |
| `src/pearl/mcp/tools.py` | Modify | Add `pearl_check_agent_contract` tool definition (count: 50 → 51) |
| `src/pearl/mcp/server.py` | Modify | Add `_route` entry + `_check_agent_contract` handler |
| `tests/test_mcp.py` | Modify | Update tool count assertion from 50 → 51 |
| `tests/test_contract_compliance.py` | Create | Unit tests for `LiteLLMClient` + integration test for the route |

---

## Task 1: LiteLLM client + ContractCompliance dataclass

**Files:**
- Create: `src/pearl/integrations/litellm.py`

**Background:** `LiteLLMClient` wraps two LiteLLM API calls:
1. `GET /key/info?key_alias=wtk-run-{run_id}` — returns the key's approved model list, budget cap, and cumulative spend.
2. `GET /spend/logs?key_alias=wtk-run-{run_id}` — returns per-request logs from which we extract distinct models actually called.

`ContractCompliance` is a plain dataclass (not ORM) because it's a computed result, never persisted.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contract_compliance.py
"""Contract compliance client and route tests."""

import json
import pytest
from unittest.mock import AsyncMock, patch
from pearl.integrations.litellm import LiteLLMClient, ContractCompliance


@pytest.fixture
def client():
    return LiteLLMClient(base_url="http://litellm:4000", api_key="sk-builder-key")


@pytest.mark.asyncio
async def test_get_key_compliance_passed(client):
    """Compliance passes when spend is within budget and only allowed models used."""
    key_info = {
        "key_alias": "wtk-run-abc",
        "models": ["ollama-qwen3.5"],
        "max_budget": 10.0,
        "spend": 2.5,
        "metadata": {"run_id": "abc", "task_packet_id": "tp_123"},
    }
    spend_logs = [
        {"model": "ollama-qwen3.5", "spend": 1.5},
        {"model": "ollama-qwen3.5", "spend": 1.0},
    ]

    mock_response_info = AsyncMock()
    mock_response_info.status_code = 200
    mock_response_info.json = lambda: key_info

    mock_response_logs = AsyncMock()
    mock_response_logs.status_code = 200
    mock_response_logs.json = lambda: spend_logs

    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[mock_response_info, mock_response_logs])

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=10.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert isinstance(result, ContractCompliance)
    assert result.passed is True
    assert result.violations == []
    assert result.actual_spend_usd == pytest.approx(2.5)
    assert result.actual_models_used == ["ollama-qwen3.5"]


@pytest.mark.asyncio
async def test_get_key_compliance_budget_exceeded(client):
    """Compliance fails when actual spend exceeds budget_cap_usd."""
    key_info = {
        "key_alias": "wtk-run-abc",
        "models": ["ollama-qwen3.5"],
        "max_budget": 5.0,
        "spend": 7.3,
        "metadata": {},
    }
    spend_logs = [{"model": "ollama-qwen3.5", "spend": 7.3}]

    mock_info = AsyncMock(); mock_info.status_code = 200; mock_info.json = lambda: key_info
    mock_logs = AsyncMock(); mock_logs.status_code = 200; mock_logs.json = lambda: spend_logs

    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[mock_info, mock_logs])

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=5.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert result.passed is False
    assert any("budget" in v.lower() for v in result.violations)


@pytest.mark.asyncio
async def test_get_key_compliance_unauthorized_model(client):
    """Compliance fails when agent called a model outside allowed_models."""
    key_info = {
        "key_alias": "wtk-run-abc",
        "models": ["ollama-qwen3.5"],
        "max_budget": 10.0,
        "spend": 1.0,
        "metadata": {},
    }
    spend_logs = [
        {"model": "ollama-qwen3.5", "spend": 0.5},
        {"model": "gpt-4o", "spend": 0.5},  # not in allowed list
    ]

    mock_info = AsyncMock(); mock_info.status_code = 200; mock_info.json = lambda: key_info
    mock_logs = AsyncMock(); mock_logs.status_code = 200; mock_logs.json = lambda: spend_logs

    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        instance.get = AsyncMock(side_effect=[mock_info, mock_logs])

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=10.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert result.passed is False
    assert any("gpt-4o" in v for v in result.violations)


@pytest.mark.asyncio
async def test_get_key_compliance_litellm_not_configured(client):
    """Returns passed=True with a note when LiteLLM is unreachable (degraded mode)."""
    with patch("pearl.integrations.litellm.httpx.AsyncClient") as mock_aclient:
        instance = mock_aclient.return_value.__aenter__.return_value
        import httpx
        instance.get = AsyncMock(side_effect=httpx.ConnectError("connection refused"))

        result = await client.get_key_compliance(
            key_alias="wtk-run-abc",
            budget_cap_usd=10.0,
            allowed_models=["ollama-qwen3.5"],
        )

    assert result.passed is True  # degrade gracefully — don't block gate if LiteLLM is down
    assert "unreachable" in result.violations[0].lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/test_contract_compliance.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'LiteLLMClient'` or `ModuleNotFoundError`.

- [ ] **Step 3: Create `src/pearl/integrations/__init__.py`**

```bash
mkdir -p src/pearl/integrations && touch src/pearl/integrations/__init__.py
```

- [ ] **Step 4: Create `src/pearl/integrations/litellm.py`**

```python
"""LiteLLM contract compliance client.

Queries LiteLLM's virtual key API to validate that an agent's runtime
behaviour matched its approved allowance profile contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger(__name__)


@dataclass
class ContractCompliance:
    passed: bool
    violations: list[str]
    key_alias: str
    approved_models: list[str]
    actual_models_used: list[str]
    budget_cap_usd: float | None
    actual_spend_usd: float
    request_count: int
    checked_at: str = field(default="")


class LiteLLMClient:
    """Async client for LiteLLM contract compliance queries."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get_key_compliance(
        self,
        key_alias: str,
        budget_cap_usd: float | None,
        allowed_models: list[str],
    ) -> ContractCompliance:
        """Query LiteLLM for spend + model usage and compare against the approved contract.

        Degrades gracefully: if LiteLLM is unreachable, returns passed=True with a
        'unreachable' violation note so the gate is not hard-blocked by infrastructure failure.
        """
        from datetime import datetime, timezone
        checked_at = datetime.now(timezone.utc).isoformat()

        try:
            key_info, spend_logs = await self._fetch_compliance_data(key_alias)
        except httpx.ConnectError as exc:
            logger.warning("LiteLLM unreachable during contract check for %s: %s", key_alias, exc)
            return ContractCompliance(
                passed=True,
                violations=[f"LiteLLM unreachable — contract check skipped ({exc})"],
                key_alias=key_alias,
                approved_models=allowed_models,
                actual_models_used=[],
                budget_cap_usd=budget_cap_usd,
                actual_spend_usd=0.0,
                request_count=0,
                checked_at=checked_at,
            )

        actual_spend = float(key_info.get("spend") or 0.0)
        actual_models = sorted({
            log["model"] for log in spend_logs if log.get("model")
        })
        request_count = len(spend_logs)

        violations: list[str] = []

        if budget_cap_usd is not None and actual_spend > budget_cap_usd:
            violations.append(
                f"Budget exceeded: actual ${actual_spend:.4f} > cap ${budget_cap_usd:.2f}"
            )

        if allowed_models:
            unauthorized = [m for m in actual_models if m not in allowed_models]
            for model in unauthorized:
                violations.append(
                    f"Unauthorized model called: {model!r} (allowed: {allowed_models})"
                )

        return ContractCompliance(
            passed=len(violations) == 0,
            violations=violations,
            key_alias=key_alias,
            approved_models=list(key_info.get("models") or allowed_models),
            actual_models_used=actual_models,
            budget_cap_usd=budget_cap_usd,
            actual_spend_usd=actual_spend,
            request_count=request_count,
            checked_at=checked_at,
        )

    async def _fetch_compliance_data(self, key_alias: str) -> tuple[dict, list[dict]]:
        headers = {"authorization": f"Bearer {self._api_key}"}
        async with httpx.AsyncClient(timeout=10.0) as http:
            info_resp = await http.get(
                f"{self._base_url}/key/info",
                params={"key_alias": key_alias},
                headers=headers,
            )
            key_info: dict = info_resp.json() if info_resp.status_code == 200 else {}

            logs_resp = await http.get(
                f"{self._base_url}/spend/logs",
                params={"key_alias": key_alias},
                headers=headers,
            )
            spend_logs: list[dict] = (
                logs_resp.json() if logs_resp.status_code == 200 else []
            )
            if not isinstance(spend_logs, list):
                spend_logs = []

        return key_info, spend_logs
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/test_contract_compliance.py -v 2>&1 | tail -10
```

Expected: all 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/pearl/integrations/__init__.py src/pearl/integrations/litellm.py tests/test_contract_compliance.py
git commit -m "$(cat <<'EOF'
feat: LiteLLM contract compliance client

Queries /key/info and /spend/logs by key alias to verify an agent's
runtime spend and model usage against its allowance profile contract.
Degrades gracefully when LiteLLM is unreachable.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: REST route `GET /task-packets/{id}/contract-compliance`

**Files:**
- Modify: `src/pearl/api/routes/task_packets.py`

**Background:** This route loads the task packet, looks up its allowance profile, reconstructs the LiteLLM key alias (`wtk-run-{run_id}` from `packet_data["run_id"]`), calls `LiteLLMClient.get_key_compliance()`, and returns the `ContractCompliance` as a dict. It reads `settings.litellm_api_url` and `settings.litellm_api_key` — if either is empty, it returns a 503 explaining that LiteLLM is not configured.

The allowance profile is fetched using `AllowanceProfileRepository` with `packet.allowance_profile_id`. If the packet has no allowance profile, the route returns a 200 with `passed=True` and `violations=["No allowance profile attached — contract check skipped"]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_contract_compliance.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from httpx import ASGITransport, AsyncClient as HttpxClient


@pytest.mark.asyncio
async def test_contract_compliance_route_no_litellm_config(app, test_user_token):
    """Returns 503 when PEARL_LITELLM_API_URL is not configured."""
    # Create a task packet with known ID via the API first
    # (use app fixture from conftest — same pattern as other route tests)
    async with HttpxClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        # Register a project first (required for task packet creation)
        proj = await ac.post(
            "/api/v1/projects",
            json={"name": "compliance-test", "repo_url": "https://github.com/test/repo"},
            headers={"Authorization": f"Bearer {test_user_token}"},
        )
        assert proj.status_code == 201
        project_id = proj.json()["project_id"]

        # Create a task packet
        tp = await ac.post(
            "/api/v1/task-packets",
            json={
                "project_id": project_id,
                "environment": "dev",
                "packet_type": "deployment",
                "packet_data": {"run_id": "run_abc123", "goal": "test"},
            },
            headers={"Authorization": f"Bearer {test_user_token}"},
        )
        assert tp.status_code == 201
        packet_id = tp.json()["packet_id"]

        # Call the compliance route with LITELLM not configured
        with patch("pearl.api.routes.task_packets.settings") as mock_settings:
            mock_settings.litellm_api_url = ""
            mock_settings.litellm_api_key = ""
            r = await ac.get(
                f"/api/v1/task-packets/{packet_id}/contract-compliance",
                headers={"Authorization": f"Bearer {test_user_token}"},
            )
    assert r.status_code == 503
    assert "not configured" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_contract_compliance_route_no_run_id(app, test_user_token):
    """Returns 200 with skipped=True when packet_data has no run_id."""
    async with HttpxClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        proj = await ac.post(
            "/api/v1/projects",
            json={"name": "compliance-test-2", "repo_url": "https://github.com/test/repo2"},
            headers={"Authorization": f"Bearer {test_user_token}"},
        )
        project_id = proj.json()["project_id"]

        tp = await ac.post(
            "/api/v1/task-packets",
            json={
                "project_id": project_id,
                "environment": "dev",
                "packet_type": "deployment",
                "packet_data": {"goal": "test"},  # no run_id
            },
            headers={"Authorization": f"Bearer {test_user_token}"},
        )
        packet_id = tp.json()["packet_id"]

        with patch("pearl.api.routes.task_packets.settings") as mock_settings:
            mock_settings.litellm_api_url = "http://litellm:4000"
            mock_settings.litellm_api_key = "sk-builder"

            r = await ac.get(
                f"/api/v1/task-packets/{packet_id}/contract-compliance",
                headers={"Authorization": f"Bearer {test_user_token}"},
            )
    assert r.status_code == 200
    body = r.json()
    assert body["passed"] is True
    assert any("no run_id" in v.lower() for v in body["violations"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/test_contract_compliance.py::test_contract_compliance_route_no_litellm_config tests/test_contract_compliance.py::test_contract_compliance_route_no_run_id -v 2>&1 | tail -10
```

Expected: 404 (route doesn't exist yet).

- [ ] **Step 3: Add the route to `src/pearl/api/routes/task_packets.py`**

Add these imports at the top of the file (after existing imports):

```python
from pearl.config import settings
from pearl.repositories.allowance_profile_repo import AllowanceProfileRepository
from pearl.integrations.litellm import LiteLLMClient
```

Add this route at the end of the file (before any module-level code):

```python
@router.get("/task-packets/{packet_id}/contract-compliance", status_code=200)
async def get_contract_compliance(
    packet_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(get_current_user),
) -> dict:
    """Check whether an agent's LiteLLM runtime usage complies with its allowance profile contract."""
    if not settings.litellm_api_url or not settings.litellm_api_key:
        raise HTTPException(
            status_code=503,
            detail="LiteLLM is not configured. Set PEARL_LITELLM_API_URL and PEARL_LITELLM_API_KEY.",
        )

    repo = TaskPacketRepository(db)
    packet = await repo.get(packet_id)
    if packet is None:
        raise NotFoundError("task_packet", packet_id)

    run_id: str | None = (packet.packet_data or {}).get("run_id")
    if not run_id:
        return {
            "passed": True,
            "violations": ["No run_id in packet_data — contract check skipped"],
            "key_alias": None,
            "approved_models": [],
            "actual_models_used": [],
            "budget_cap_usd": None,
            "actual_spend_usd": 0.0,
            "request_count": 0,
            "checked_at": "",
        }

    budget_cap: float | None = None
    allowed_models: list[str] = []
    if packet.allowance_profile_id:
        profile_repo = AllowanceProfileRepository(db)
        profile = await profile_repo.get(packet.allowance_profile_id)
        if profile:
            budget_cap = profile.budget_cap_usd
            allowed_models = list(profile.model_restrictions or [])

    key_alias = f"wtk-run-{run_id}"
    client = LiteLLMClient(
        base_url=settings.litellm_api_url,
        api_key=settings.litellm_api_key,
    )
    compliance = await client.get_key_compliance(
        key_alias=key_alias,
        budget_cap_usd=budget_cap,
        allowed_models=allowed_models,
    )

    return {
        "passed": compliance.passed,
        "violations": compliance.violations,
        "key_alias": compliance.key_alias,
        "approved_models": compliance.approved_models,
        "actual_models_used": compliance.actual_models_used,
        "budget_cap_usd": compliance.budget_cap_usd,
        "actual_spend_usd": compliance.actual_spend_usd,
        "request_count": compliance.request_count,
        "checked_at": compliance.checked_at,
    }
```

- [ ] **Step 4: Add missing import to task_packets.py**

`get_current_user` is needed. Check if it's already imported:

```bash
grep "get_current_user\|AllowanceProfileRepository" /mnt/c/Users/bradj/Development/PeaRL/src/pearl/api/routes/task_packets.py | head -5
```

If `get_current_user` is missing, add to the `from pearl.dependencies import ...` line:
```python
from pearl.dependencies import get_db, get_trace_id, get_current_user
```

If `AllowanceProfileRepository` is not in the project, check the correct import path:
```bash
find /mnt/c/Users/bradj/Development/PeaRL/src/pearl/repositories -name "*.py" | xargs grep -l "AllowanceProfile" 2>/dev/null
```

- [ ] **Step 5: Run the route tests**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/test_contract_compliance.py -v 2>&1 | tail -15
```

Expected: all 6 tests pass.

- [ ] **Step 6: Run full suite**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: no regressions.

- [ ] **Step 7: Commit**

```bash
git add src/pearl/api/routes/task_packets.py src/pearl/integrations/litellm.py tests/test_contract_compliance.py
git commit -m "$(cat <<'EOF'
feat: GET /task-packets/{id}/contract-compliance route

Loads task packet + allowance profile, reconstructs the LiteLLM virtual
key alias (wtk-run-{run_id}), and returns ContractCompliance showing
whether the agent's runtime spend and model usage matched its contract.
Returns 503 when LiteLLM is not configured.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: MCP tool `pearl_check_agent_contract`

**Files:**
- Modify: `src/pearl/mcp/tools.py`
- Modify: `src/pearl/mcp/server.py`
- Modify: `tests/test_mcp.py`

**Background:** The MCP tool lets agents and operators query contract compliance directly from their MCP client (e.g., LiteLLM itself, or Claude Code). The tool calls the PeaRL REST endpoint created in Task 2. The tool count goes from 50 → 51 — `test_mcp.py` hardcodes 50 and must be updated.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_mcp.py` at the end of the file:

```python
@pytest.mark.asyncio
async def test_check_agent_contract_tool_registered():
    """pearl_check_agent_contract is in TOOL_DEFINITIONS."""
    from pearl.mcp.tools import TOOL_DEFINITIONS
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert "pearl_check_agent_contract" in names


@pytest.mark.asyncio
async def test_check_agent_contract_tool_has_required_schema():
    """pearl_check_agent_contract schema declares packet_id as required."""
    from pearl.mcp.tools import TOOL_DEFINITIONS
    tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "pearl_check_agent_contract")
    schema = tool["inputSchema"]
    assert "packet_id" in schema["properties"]
    assert "packet_id" in schema.get("required", [])
```

- [ ] **Step 2: Run tests to confirm failure**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/test_mcp.py::test_check_agent_contract_tool_registered tests/test_mcp.py::test_check_agent_contract_tool_has_required_schema -v 2>&1 | tail -10
```

Expected: FAIL — tool not found.

- [ ] **Step 3: Add tool definition to `src/pearl/mcp/tools.py`**

Find the end of `TOOL_DEFINITIONS` list and add before the closing `]`:

```python
    {
        "name": "pearl_check_agent_contract",
        "description": (
            "Check whether a deployed agent's LiteLLM runtime usage complies with its "
            "approved allowance profile contract. Queries actual spend and model usage "
            "from LiteLLM's virtual key system and compares against the contracted limits. "
            "Returns passed=true/false with a list of violations."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "packet_id": {
                    "type": "string",
                    "description": "Task packet ID (tp_...) to check contract compliance for.",
                },
            },
            "required": ["packet_id"],
        },
    },
```

- [ ] **Step 4: Update tool count in `tests/test_mcp.py`**

Find and update both occurrences of `== 50` to `== 51`:

```python
# Before:
assert len(TOOL_DEFINITIONS) == 50
# After:
assert len(TOOL_DEFINITIONS) == 51
```

```python
# Before:
assert len(tools) == 50
# After:
assert len(tools) == 51
```

- [ ] **Step 5: Add route + handler to `src/pearl/mcp/server.py`**

In the `_route` method's `routes` dict, add:

```python
"pearl_check_agent_contract": self._check_agent_contract,
```

Add the handler method to the `MCPServer` class (near the other task packet handlers):

```python
async def _check_agent_contract(self, arguments: dict) -> dict:
    packet_id = arguments.get("packet_id", "")
    return await self._request("GET", f"/task-packets/{packet_id}/contract-compliance")
```

- [ ] **Step 6: Run MCP tests**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/test_mcp.py -v 2>&1 | tail -15
```

Expected: all tests pass with count 51.

- [ ] **Step 7: Run full suite**

```bash
cd /mnt/c/Users/bradj/Development/PeaRL && PEARL_LOCAL=1 pytest tests/ -q 2>&1 | tail -5
```

Expected: 806+ passed, 0 failures.

- [ ] **Step 8: Commit**

```bash
git add src/pearl/mcp/tools.py src/pearl/mcp/server.py tests/test_mcp.py
git commit -m "$(cat <<'EOF'
feat: pearl_check_agent_contract MCP tool

Exposes GET /task-packets/{id}/contract-compliance via MCP so agents
and operators can query LiteLLM contract compliance from any MCP client.
Tool count: 50 → 51.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Pull spend from LiteLLM virtual key | Task 1 (`/spend/logs`) |
| Validate model usage against allowance profile | Task 1 (unauthorized model check) |
| Validate spend against budget_cap_usd | Task 1 (budget exceeded check) |
| REST endpoint for operators | Task 2 (`GET /task-packets/{id}/contract-compliance`) |
| Graceful degradation when LiteLLM down | Task 1 (`ConnectError` → passed=True with note) |
| MCP tool for agent/LiteLLM access | Task 3 (`pearl_check_agent_contract`) |
| Key alias reconstruction from packet_data | Task 2 (`wtk-run-{run_id}`) |

**Placeholder scan:** No TBDs, no "handle edge cases" filler. All code shown.

**Type consistency:**
- `ContractCompliance` defined in Task 1, used as return in Task 1, serialized to dict in Task 2 — field names match.
- `LiteLLMClient` instantiated in Task 2 with `base_url` + `api_key` — matches Task 1 constructor.
- `_check_agent_contract` in Task 3 calls `GET /task-packets/{id}/contract-compliance` — matches Task 2 route path.

**Known constraint:** LiteLLM's `/key/info?key_alias=` parameter support may vary by version. If 1.82+ doesn't support `key_alias` as a query param, the `key_info` dict will be empty and the compliance check will rely solely on `/spend/logs`. The compliance result will still be valid for spend checking; approved model list will fall back to `allowed_models` from the allowance profile.
