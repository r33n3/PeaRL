"""Contract tests for report generation."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _setup_full_project(client):
    """Set up a fully compiled project with approved approval."""
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
async def test_report_generation_contract(client):
    """POST reports/generate returns a valid report."""
    pid = await _setup_full_project(client)
    req = load_example("reports/generate-report.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/reports/generate", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["report_type"] == req["report_type"]
    assert body["status"] == "ready"
    assert body["format"] == req["format"]
    assert "content" in body


@pytest.mark.asyncio
async def test_release_readiness_no_blockers(client):
    """Release readiness with no pending approvals is ready."""
    pid = await _setup_full_project(client)
    req = load_example("reports/generate-report.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/reports/generate", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["content"]["summary"]["ready"] is True


@pytest.mark.asyncio
async def test_release_readiness_with_blocker(client):
    """Release readiness with pending approval has blockers."""
    pid = await _setup_full_project(client)

    # Create a pending approval
    approval = load_example("approvals/create-approval.request.json")
    approval["project_id"] = pid
    await client.post("/api/v1/approvals/requests", json=approval)

    req = load_example("reports/generate-report.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/reports/generate", json=req)
    assert r.status_code == 200
    body = r.json()
    assert body["content"]["summary"]["ready"] is False
    assert len(body["content"]["blockers"]) > 0
