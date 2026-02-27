"""Tests for the agent-brief endpoint.

Covers:
- GET /projects/{id}/promotions/agent-brief returns 200 for an existing project
- Response contains required top-level fields: current_stage, next_stage, gate_status,
  ready_to_elevate, open_task_packets, blockers_count
- open_task_packets is a list
- blockers_count is an integer
- gate_status defaults to "not_evaluated" when no evaluation has been run
- ready_to_elevate is False when gate has not been evaluated
- After evaluation, gate_status reflects the evaluation result
- 404 returned for non-existent project
"""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project(client, project_id: str, ai_enabled: bool = False) -> str:
    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    project["ai_enabled"] = ai_enabled
    r = await client.post("/api/v1/projects", json=project)
    assert r.status_code == 201
    return project_id


async def _setup_full_project(client, project_id: str, ai_enabled: bool = False) -> str:
    await _create_project(client, project_id, ai_enabled)

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{project_id}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{project_id}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{project_id}/environment-profile", json=profile)

    return project_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agent_brief_not_found(client):
    """GET /projects/{id}/promotions/agent-brief returns 404 for unknown project."""
    r = await client.get("/api/v1/projects/proj_nonexistent_brief/promotions/agent-brief")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_agent_brief_returns_200(client):
    """GET /projects/{id}/promotions/agent-brief returns 200 for an existing project."""
    pid = await _create_project(client, "proj_brief_200")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_agent_brief_required_fields(client):
    """Agent brief response contains all required top-level fields."""
    pid = await _create_project(client, "proj_brief_fields")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    assert r.status_code == 200
    data = r.json()

    required_fields = [
        "project_id",
        "current_stage",
        "next_stage",
        "gate_status",
        "ready_to_elevate",
        "open_task_packets",
        "blockers_count",
    ]
    for field in required_fields:
        assert field in data, f"Missing required field: {field}"


@pytest.mark.asyncio
async def test_agent_brief_open_task_packets_is_list(client):
    """open_task_packets is a list (possibly empty)."""
    pid = await _create_project(client, "proj_brief_tp_list")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    data = r.json()
    assert isinstance(data["open_task_packets"], list)


@pytest.mark.asyncio
async def test_agent_brief_blockers_count_is_integer(client):
    """blockers_count is an integer."""
    pid = await _create_project(client, "proj_brief_blockers_int")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    data = r.json()
    assert isinstance(data["blockers_count"], int)


@pytest.mark.asyncio
async def test_agent_brief_not_evaluated_defaults(client):
    """When no evaluation has been run, gate_status is 'not_evaluated' and ready_to_elevate is False."""
    pid = await _create_project(client, "proj_brief_no_eval")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    data = r.json()
    assert data["gate_status"] == "not_evaluated"
    assert data["ready_to_elevate"] is False
    assert data["blockers_count"] == 0


@pytest.mark.asyncio
async def test_agent_brief_current_stage_default(client):
    """current_stage defaults to 'sandbox' when no environment profile has been set."""
    pid = await _create_project(client, "proj_brief_stage_default")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    data = r.json()
    assert data["current_stage"] == "sandbox"


@pytest.mark.asyncio
async def test_agent_brief_after_evaluation(client):
    """After evaluation, gate_status reflects the evaluation result and blockers_count is set."""
    pid = await _setup_full_project(client, "proj_brief_after_eval")

    eval_r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert eval_r.status_code == 200
    eval_data = eval_r.json()
    expected_status = eval_data["status"]

    brief_r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    assert brief_r.status_code == 200
    brief_data = brief_r.json()

    assert brief_data["gate_status"] == expected_status
    assert isinstance(brief_data["blockers_count"], int)
    assert brief_data["blockers_count"] >= 0


@pytest.mark.asyncio
async def test_agent_brief_ready_to_elevate_false_when_failed(client):
    """ready_to_elevate is False when gate evaluation status is not 'passed'."""
    pid = "proj_brief_not_ready"
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    # No baseline → gate will fail
    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)
    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")

    brief_r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    data = brief_r.json()

    if data["gate_status"] != "passed":
        assert data["ready_to_elevate"] is False


@pytest.mark.asyncio
async def test_agent_brief_project_id_in_response(client):
    """The project_id in the response matches the requested project."""
    pid = await _create_project(client, "proj_brief_pid_match")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    data = r.json()
    assert data["project_id"] == pid


@pytest.mark.asyncio
async def test_agent_brief_resolved_requirements_field(client):
    """resolved_requirements field is present in the response."""
    pid = await _setup_full_project(client, "proj_brief_resolved_reqs")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/agent-brief")
    data = r.json()
    assert "resolved_requirements" in data
    assert isinstance(data["resolved_requirements"], list)
