"""Contract tests for findings ingestion and remediation generation."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _setup_compiled_project(client):
    """Full project setup through compilation."""
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
async def test_findings_ingest_contract(client):
    """POST /findings/ingest accepts findings with partial acceptance support."""
    req = load_example("findings/findings-ingest.request.json")
    r = await client.post("/api/v1/findings/ingest", json=req)
    assert r.status_code == 202
    body = r.json()
    assert "accepted_count" in body
    assert "quarantined_count" in body
    assert "batch_id" in body
    assert body["accepted_count"] >= 1


@pytest.mark.asyncio
async def test_remediation_spec_contract(client):
    """POST remediation-specs/generate returns a valid remediation spec."""
    pid = await _setup_compiled_project(client)

    # Ingest findings first
    findings_req = load_example("findings/findings-ingest.request.json")
    await client.post("/api/v1/findings/ingest", json=findings_req)

    # Generate remediation spec
    rem_req = load_example("remediation/generate-remediation-spec.request.json")
    r = await client.post(
        f"/api/v1/projects/{pid}/remediation-specs/generate", json=rem_req
    )
    assert r.status_code == 201
    body = r.json()
    assert body["eligibility"] in ("auto_allowed", "auto_allowed_with_approval", "human_required")
    assert "approval_required" in body
    assert "required_tests" in body
    assert len(body["required_tests"]) > 0
    assert "risk_summary" in body
