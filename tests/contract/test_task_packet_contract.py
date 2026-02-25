"""Contract tests for task packet generation."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _setup_compiled_project(client):
    """Create project, attach inputs, and compile."""
    project = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project)
    pid = project["project_id"]

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    compile_req = load_example("compile/compile-context.request.json")
    await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)
    return pid


@pytest.mark.asyncio
async def test_task_packet_generation_contract(client):
    """POST task-packets returns a valid task packet with actions and triggers."""
    pid = await _setup_compiled_project(client)
    tp_req = load_example("task-packets/generate-task-packet.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/task-packets", json=tp_req)
    assert r.status_code == 201
    tp = r.json()
    assert tp["task_type"] == tp_req["task_type"]
    assert tp["environment"] == tp_req["environment"]
    assert "allowed_actions" in tp
    assert "blocked_actions" in tp
    assert "approval_triggers" in tp
    assert "task_packet_id" in tp


@pytest.mark.asyncio
async def test_task_packet_requires_compiled_package(client):
    """Task packet generation without compiled package returns 404."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_tp_contract"
    await client.post("/api/v1/projects", json=project)

    tp_req = {
        "schema_version": "1.1",
        "task_type": "feature",
        "task_summary": "Test",
        "environment": "dev",
        "trace_id": "trc_tp_contract",
    }
    r = await client.post("/api/v1/projects/proj_tp_contract/task-packets", json=tp_req)
    assert r.status_code == 404
