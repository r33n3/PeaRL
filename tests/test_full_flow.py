"""End-to-end flow test: project -> inputs -> compile -> task packet
   -> findings -> remediation -> approval -> exception -> report."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_full_flow(client):
    """Exercise the complete happy path through all major endpoints."""

    # 1. Create project
    project = load_example("project/create-project.request.json")
    r = await client.post("/api/v1/projects", json=project)
    assert r.status_code == 201
    assert r.json()["project_id"] == "proj_customer_support_ai"

    # 2. Attach org baseline
    baseline = load_example("project/org-baseline.request.json")
    r = await client.post("/api/v1/projects/proj_customer_support_ai/org-baseline", json=baseline)
    assert r.status_code == 200
    assert r.json()["kind"] == "PearlOrgBaseline"

    # 3. Attach app spec
    spec = load_example("project/app-spec.request.json")
    r = await client.post("/api/v1/projects/proj_customer_support_ai/app-spec", json=spec)
    assert r.status_code == 200
    assert r.json()["kind"] == "PearlApplicationSpec"

    # 4. Attach environment profile
    profile = load_example("project/environment-profile.request.json")
    r = await client.post("/api/v1/projects/proj_customer_support_ai/environment-profile", json=profile)
    assert r.status_code == 200
    assert r.json()["profile_id"] == "envp_preprod_supervised_high"

    # 5. Compile context
    compile_req = load_example("compile/compile-context.request.json")
    r = await client.post("/api/v1/projects/proj_customer_support_ai/compile-context", json=compile_req)
    assert r.status_code == 202
    job_data = r.json()
    assert job_data["job_type"] == "compile_context"
    job_id = job_data["job_id"]

    # 6. Get job status
    r = await client.get(f"/api/v1/jobs/{job_id}")
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"

    # 7. Get compiled package
    r = await client.get("/api/v1/projects/proj_customer_support_ai/compiled-package")
    assert r.status_code == 200
    pkg = r.json()
    assert pkg["kind"] == "PearlCompiledContextPackage"
    assert pkg["autonomy_policy"]["mode"] == "supervised_autonomous"
    assert "authz_checks" in pkg["security_requirements"]["required_controls"]
    assert pkg["responsible_ai_requirements"]["transparency"]["ai_disclosure_required"] is True
    assert pkg["network_requirements"]["public_egress_forbidden"] is True

    # 8. Generate task packet
    tp_req = load_example("task-packets/generate-task-packet.request.json")
    r = await client.post("/api/v1/projects/proj_customer_support_ai/task-packets", json=tp_req)
    assert r.status_code == 201
    tp = r.json()
    assert tp["task_type"] == "refactor"
    assert tp["environment"] == "preprod"
    assert len(tp["allowed_actions"]) > 0
    assert len(tp["blocked_actions"]) > 0
    assert "auth_flow_change" in tp["approval_triggers"]

    # 9. Ingest findings
    findings_req = load_example("findings/findings-ingest.request.json")
    r = await client.post("/api/v1/findings/ingest", json=findings_req)
    assert r.status_code == 202
    ingest = r.json()
    assert ingest["accepted_count"] == 1
    assert ingest["quarantined_count"] == 0

    # 10. Generate remediation spec
    rem_req = load_example("remediation/generate-remediation-spec.request.json")
    r = await client.post(
        "/api/v1/projects/proj_customer_support_ai/remediation-specs/generate",
        json=rem_req,
    )
    assert r.status_code == 201
    rem = r.json()
    assert rem["eligibility"] in ("auto_allowed", "auto_allowed_with_approval", "human_required")
    assert rem["approval_required"] is True
    assert len(rem["required_tests"]) > 0

    # 11. Create approval request
    approval_req = load_example("approvals/create-approval.request.json")
    r = await client.post("/api/v1/approvals/requests", json=approval_req)
    assert r.status_code == 201
    assert r.json()["status"] == "pending"

    # 12. Decide approval
    decision = load_example("approvals/decision.request.json")
    r = await client.post("/api/v1/approvals/appr_network_change_001/decide", json=decision)
    assert r.status_code == 200
    assert r.json()["decision"] == "approve"

    # 13. Create exception
    exception = load_example("exceptions/create-exception.request.json")
    r = await client.post("/api/v1/exceptions", json=exception)
    assert r.status_code == 201
    assert r.json()["status"] == "active"

    # 14. Generate report
    report_req = load_example("reports/generate-report.request.json")
    r = await client.post("/api/v1/projects/proj_customer_support_ai/reports/generate", json=report_req)
    assert r.status_code == 200
    report = r.json()
    assert report["report_type"] == "release_readiness"
    assert report["status"] == "ready"
    assert report["format"] == "json"
    assert "content" in report
    # The approval was already approved, so no blockers
    assert report["content"]["summary"]["ready"] is True


@pytest.mark.asyncio
async def test_compile_missing_inputs(client):
    """Compilation should fail if inputs are missing."""
    # Create project but don't attach inputs
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_incomplete"
    await client.post("/api/v1/projects", json=project)

    compile_req = {
        "schema_version": "1.1",
        "project_id": "proj_incomplete",
        "compile_options": {},
        "trace_id": "trc_test_compile",
    }
    r = await client.post("/api/v1/projects/proj_incomplete/compile-context", json=compile_req)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_task_packet_without_compiled_package(client):
    """Task packet should fail if no compiled package exists."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_no_compile"
    await client.post("/api/v1/projects", json=project)

    tp_req = {
        "schema_version": "1.1",
        "task_type": "feature",
        "task_summary": "Test task",
        "environment": "dev",
        "trace_id": "trc_test_tp",
    }
    r = await client.post("/api/v1/projects/proj_no_compile/task-packets", json=tp_req)
    assert r.status_code == 404
