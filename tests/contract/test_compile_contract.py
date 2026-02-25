"""Contract tests for context compilation endpoints."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _setup_project_with_inputs(client):
    """Helper: create project and attach all three inputs."""
    project = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project)
    pid = project["project_id"]

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    return pid


@pytest.mark.asyncio
async def test_compile_context_contract(client):
    """POST compile-context returns 202 with job status."""
    pid = await _setup_project_with_inputs(client)
    compile_req = load_example("compile/compile-context.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)
    assert r.status_code == 202
    body = r.json()
    assert body["job_type"] == "compile_context"
    assert body["status"] in ("queued", "running", "succeeded")
    assert "job_id" in body


@pytest.mark.asyncio
async def test_compiled_package_contract(client):
    """GET compiled-package returns a valid PearlCompiledContextPackage."""
    pid = await _setup_project_with_inputs(client)
    compile_req = load_example("compile/compile-context.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)
    assert r.status_code == 202

    r = await client.get(f"/api/v1/projects/{pid}/compiled-package")
    assert r.status_code == 200
    pkg = r.json()
    assert pkg["kind"] == "PearlCompiledContextPackage"
    assert "autonomy_policy" in pkg
    assert "security_requirements" in pkg
    assert "responsible_ai_requirements" in pkg
    assert "integrity" in pkg["package_metadata"]


@pytest.mark.asyncio
async def test_compile_requires_inputs(client):
    """Compilation without inputs returns 400."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_compile_contract_test"
    await client.post("/api/v1/projects", json=project)

    compile_req = {
        "schema_version": "1.1",
        "project_id": "proj_compile_contract_test",
        "compile_options": {},
        "trace_id": "trc_contract",
    }
    r = await client.post(
        "/api/v1/projects/proj_compile_contract_test/compile-context",
        json=compile_req,
    )
    assert r.status_code == 400
