"""API tests for project endpoints using example payloads."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_create_project(client):
    data = load_example("project/create-project.request.json")
    response = await client.post("/api/v1/projects", json=data)
    assert response.status_code == 201
    body = response.json()
    assert body["project_id"] == "proj_customer_support_ai"
    assert body["name"] == "Customer Support AI Assistant"
    assert body["ai_enabled"] is True
    assert "created_at" in body
    assert "traceability" in body
    assert "X-Trace-Id" in response.headers


@pytest.mark.asyncio
async def test_create_project_duplicate(client):
    data = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=data)
    response = await client.post("/api/v1/projects", json=data)
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_project(client):
    data = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=data)

    response = await client.get("/api/v1/projects/proj_customer_support_ai")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == "proj_customer_support_ai"


@pytest.mark.asyncio
async def test_get_project_not_found(client):
    response = await client.get("/api/v1/projects/proj_nonexistent")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_update_project(client):
    data = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=data)

    data["name"] = "Updated Name"
    response = await client.put("/api/v1/projects/proj_customer_support_ai", json=data)
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_upsert_org_baseline(client):
    # Create project first
    project_data = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project_data)

    baseline_data = load_example("project/org-baseline.request.json")
    response = await client.post(
        "/api/v1/projects/proj_customer_support_ai/org-baseline",
        json=baseline_data,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "PearlOrgBaseline"
    assert body["baseline_id"] == "orgb_secure_autonomous_v1"


@pytest.mark.asyncio
async def test_upsert_app_spec(client):
    project_data = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project_data)

    spec_data = load_example("project/app-spec.request.json")
    response = await client.post(
        "/api/v1/projects/proj_customer_support_ai/app-spec",
        json=spec_data,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "PearlApplicationSpec"
    assert body["application"]["app_id"] == "customer-support-ai-assistant"


@pytest.mark.asyncio
async def test_upsert_environment_profile(client):
    project_data = load_example("project/create-project.request.json")
    await client.post("/api/v1/projects", json=project_data)

    profile_data = load_example("project/environment-profile.request.json")
    response = await client.post(
        "/api/v1/projects/proj_customer_support_ai/environment-profile",
        json=profile_data,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["profile_id"] == "envp_preprod_supervised_high"
    assert body["autonomy_mode"] == "supervised_autonomous"


@pytest.mark.asyncio
async def test_sub_resource_on_missing_project(client):
    baseline_data = load_example("project/org-baseline.request.json")
    response = await client.post(
        "/api/v1/projects/proj_nonexistent/org-baseline",
        json=baseline_data,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_trace_id_propagation(client):
    data = load_example("project/create-project.request.json")
    response = await client.post(
        "/api/v1/projects",
        json=data,
        headers={"X-Trace-Id": "trc_custom_12345678"},
    )
    assert response.headers["X-Trace-Id"] == "trc_custom_12345678"
