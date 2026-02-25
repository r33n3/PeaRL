"""Contract tests for project endpoints using spec example payloads."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_create_project_contract(client):
    """POST /projects returns spec-compliant response."""
    request = load_example("project/create-project.request.json")
    r = await client.post("/api/v1/projects", json=request)
    assert r.status_code == 201
    body = r.json()
    assert body["project_id"] == request["project_id"]
    assert body["schema_version"] == "1.1"
    assert "name" in body
    assert "owner_team" in body


@pytest.mark.asyncio
async def test_get_project_contract(client):
    """GET /projects/{id} returns stored project."""
    request = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=request)
    r = await client.get(f"/api/v1/projects/{request['project_id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["project_id"] == request["project_id"]


@pytest.mark.asyncio
async def test_org_baseline_contract(client):
    """POST org-baseline accepts spec example and returns PearlOrgBaseline."""
    project = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project)
    baseline = load_example("project/org-baseline.request.json")
    r = await client.post(
        f"/api/v1/projects/{project['project_id']}/org-baseline", json=baseline
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "PearlOrgBaseline"


@pytest.mark.asyncio
async def test_app_spec_contract(client):
    """POST app-spec accepts spec example and returns PearlApplicationSpec."""
    project = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project)
    spec = load_example("project/app-spec.request.json")
    r = await client.post(
        f"/api/v1/projects/{project['project_id']}/app-spec", json=spec
    )
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "PearlApplicationSpec"


@pytest.mark.asyncio
async def test_environment_profile_contract(client):
    """POST environment-profile accepts spec example."""
    project = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project)
    profile = load_example("project/environment-profile.request.json")
    r = await client.post(
        f"/api/v1/projects/{project['project_id']}/environment-profile",
        json=profile,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["profile_id"] == profile["profile_id"]
