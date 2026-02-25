"""End-to-end contract test: exercises the complete happy path through all major endpoints.

This is the master contract test that validates the full lifecycle:
project -> inputs -> compile -> task packet -> findings -> remediation
-> approval -> exception -> report.
"""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[2] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_full_lifecycle_contract(client):
    """Complete happy path validates all endpoint contracts in sequence."""

    # 1. Create project
    project = load_example("project/create-project.request.json")
    r = await client.post("/api/v1/projects", json=project)
    assert r.status_code == 201
    pid = r.json()["project_id"]

    # 2. Attach org baseline
    baseline = load_example("project/org-baseline.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)
    assert r.status_code == 200
    assert r.json()["kind"] == "PearlOrgBaseline"

    # 3. Attach app spec
    spec = load_example("project/app-spec.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)
    assert r.status_code == 200
    assert r.json()["kind"] == "PearlApplicationSpec"

    # 4. Attach environment profile
    profile = load_example("project/environment-profile.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)
    assert r.status_code == 200

    # 5. Compile context
    compile_req = load_example("compile/compile-context.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)
    assert r.status_code == 202
    job_id = r.json()["job_id"]

    # 6. Poll job status
    r = await client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"

    # 7. Get compiled package
    r = await client.get(f"/api/v1/projects/{pid}/compiled-package")
    assert r.status_code == 200
    pkg = r.json()
    assert pkg["kind"] == "PearlCompiledContextPackage"
    assert "integrity" in pkg["package_metadata"]
    assert pkg["package_metadata"]["integrity"]["hash_alg"] == "sha256"

    # 8. Generate task packet
    tp_req = load_example("task-packets/generate-task-packet.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/task-packets", json=tp_req)
    assert r.status_code == 201
    tp = r.json()
    assert len(tp["allowed_actions"]) > 0
    assert len(tp["blocked_actions"]) > 0

    # 9. Ingest findings
    findings_req = load_example("findings/findings-ingest.request.json")
    r = await client.post("/api/v1/findings/ingest", json=findings_req)
    assert r.status_code == 202
    assert r.json()["accepted_count"] == 1

    # 10. Generate remediation spec
    rem_req = load_example("remediation/generate-remediation-spec.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/remediation-specs/generate", json=rem_req)
    assert r.status_code == 201
    rem = r.json()
    assert "eligibility" in rem
    assert rem["approval_required"] is True

    # 11. Create approval request
    approval_req = load_example("approvals/create-approval.request.json")
    r = await client.post("/api/v1/approvals/requests", json=approval_req)
    assert r.status_code == 201
    assert r.json()["status"] == "pending"

    # 12. Decide approval
    decision = load_example("approvals/decision.request.json")
    r = await client.post(
        f"/api/v1/approvals/{approval_req['approval_request_id']}/decide",
        json=decision,
    )
    assert r.status_code == 200
    assert r.json()["decision"] == "approve"

    # 13. Create exception
    exception = load_example("exceptions/create-exception.request.json")
    r = await client.post("/api/v1/exceptions", json=exception)
    assert r.status_code == 201
    assert r.json()["status"] == "active"

    # 14. Generate report
    report_req = load_example("reports/generate-report.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/reports/generate", json=report_req)
    assert r.status_code == 200
    report = r.json()
    assert report["report_type"] == "release_readiness"
    assert report["status"] == "ready"
    assert report["content"]["summary"]["ready"] is True


@pytest.mark.asyncio
async def test_trace_id_propagation_contract(client):
    """All responses include trace_id when X-Trace-Id header is provided."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_trace_contract"
    headers = {"X-Trace-Id": "trc_contract_test_12345"}
    r = await client.post("/api/v1/projects", json=project, headers=headers)
    assert r.status_code == 201
    # Trace ID should be echoed in response headers
    assert r.headers.get("x-trace-id") == "trc_contract_test_12345"


@pytest.mark.asyncio
async def test_not_found_error_contract(client):
    """404 responses use spec-compliant error format."""
    r = await client.get("/api/v1/projects/proj_nonexistent_xyz")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "NOT_FOUND"
