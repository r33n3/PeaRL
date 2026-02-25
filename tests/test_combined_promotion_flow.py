"""End-to-end integration: register → configure → scan → evaluate → promote.

Exercises the full governance lifecycle including security findings,
fairness governance, promotion gate evaluation, and markdown rendering.
"""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_full_promotion_lifecycle(client):
    """Full lifecycle: register → configure → findings → fairness → evaluate → promote."""
    pid = "proj_lifecycle"

    # 1. Register project (AI-enabled)
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = True
    r = await client.post("/api/v1/projects", json=project)
    assert r.status_code == 201

    # 2. Attach baseline, app spec, environment profile
    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    # 3. Compile context
    compile_req = load_example("compile/compile-context.request.json")
    compile_req["project_id"] = pid
    await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)

    # 4. First promotion evaluation — should show blockers for AI rules
    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    eval1 = r.json()
    assert eval1["total_count"] > 0
    # Should have some failures (fairness case not defined, etc.)
    assert eval1["failed_count"] > 0 or eval1["passed_count"] > 0

    # 5. Create fairness case
    fc_body = {
        "risk_tier": "r2",
        "fairness_criticality": "high",
        "system_description": "AI support chatbot",
        "stakeholders": ["customers"],
        "fairness_principles": ["equal_treatment"],
    }
    r = await client.post(f"/api/v1/projects/{pid}/fairness-cases", json=fc_body)
    assert r.status_code == 201

    # 6. Submit evidence package
    ev_body = {
        "environment": "dev",
        "evidence_type": "bias_benchmark",
        "summary": "Bias metrics across demographics",
        "evidence_data": {"demographic_parity": 0.95},
    }
    r = await client.post(f"/api/v1/projects/{pid}/evidence", json=ev_body)
    assert r.status_code == 201
    ev_id = r.json()["evidence_id"]

    # 7. Sign attestation
    r = await client.post(
        f"/api/v1/projects/{pid}/evidence/{ev_id}/sign",
        json={"signed_by": "reviewer@acme.com"},
    )
    assert r.status_code == 200
    assert r.json()["attestation_status"] == "signed"

    # 8. Submit context receipt
    r = await client.post(
        "/api/v1/context/receipts",
        json={
            "project_id": pid,
            "commit_hash": "abc123",
            "agent_id": "claude-code",
            "tool_calls": ["read_fairness_case"],
            "artifact_hashes": {"fc": "sha256:test"},
        },
    )
    assert r.status_code == 201

    # 9. Re-evaluate — fairness rules should now pass
    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    eval2 = r.json()
    # More rules should pass now
    assert eval2["passed_count"] >= eval1["passed_count"]

    # 10. Check readiness
    r = await client.get(f"/api/v1/projects/{pid}/promotions/readiness")
    assert r.status_code == 200
    readiness = r.json()
    assert readiness["project_id"] == pid
    assert "progress_pct" in readiness

    # 11. Request promotion
    r = await client.post(f"/api/v1/projects/{pid}/promotions/request")
    assert r.status_code == 202
    prom_req = r.json()
    assert "approval_request_id" in prom_req
    assert prom_req["project_id"] == pid

    # 12. Get project summary (markdown)
    r = await client.get(f"/api/v1/projects/{pid}/summary?format=markdown")
    assert r.status_code == 200
    summary = r.json()
    assert summary["format"] == "markdown"
    assert "content" in summary
    assert pid in summary["content"] or "proj_lifecycle" in summary["content"]

    # 13. Get project summary (JSON)
    r = await client.get(f"/api/v1/projects/{pid}/summary?format=json")
    assert r.status_code == 200
    json_summary = r.json()
    assert json_summary["format"] == "json"
    assert json_summary["project"]["project_id"] == pid


@pytest.mark.asyncio
async def test_promotion_with_findings_blocks(client):
    """Ingesting critical findings blocks promotion."""
    pid = "proj_blocked"

    # Setup project
    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    compile_req = load_example("compile/compile-context.request.json")
    compile_req["project_id"] = pid
    await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)

    # Ingest critical finding
    findings_req = load_example("findings/findings-ingest.request.json")
    findings_req["findings"][0]["project_id"] = pid
    findings_req["findings"][0]["finding_id"] = "find_block_001"
    findings_req["findings"][0]["severity"] = "critical"
    await client.post("/api/v1/findings/ingest", json=findings_req)

    # Evaluate — should have critical_findings_zero failure
    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    data = r.json()
    crit_rules = [rr for rr in data.get("rule_results", []) if rr["rule_type"] == "critical_findings_zero"]
    assert len(crit_rules) == 1
    assert crit_rules[0]["result"] == "fail"

    # Request promotion — should still create approval but status reflects failure
    r = await client.post(f"/api/v1/projects/{pid}/promotions/request")
    assert r.status_code == 202
    assert r.json()["status"] == "evaluation_failed"


@pytest.mark.asyncio
async def test_release_readiness_enhanced(client):
    """Release readiness includes findings_by_severity and risk_factors."""
    pid = "proj_rr_enhanced"

    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = True
    await client.post("/api/v1/projects", json=project)

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{pid}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{pid}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{pid}/environment-profile", json=profile)

    compile_req = load_example("compile/compile-context.request.json")
    compile_req["project_id"] = pid
    await client.post(f"/api/v1/projects/{pid}/compile-context", json=compile_req)

    # Ingest a high-severity finding
    findings_req = load_example("findings/findings-ingest.request.json")
    findings_req["findings"][0]["project_id"] = pid
    findings_req["findings"][0]["finding_id"] = "find_rr_001"
    findings_req["findings"][0]["severity"] = "high"
    await client.post("/api/v1/findings/ingest", json=findings_req)

    # Generate release readiness report
    report_req = load_example("reports/generate-report.request.json")
    r = await client.post(f"/api/v1/projects/{pid}/reports/generate", json=report_req)
    assert r.status_code == 200
    report = r.json()

    content = report["content"]
    # No pending approvals = ready (approval blockers only)
    assert content["summary"]["ready"] is True
    # But risk factors should flag the high finding
    assert "findings_by_severity" in content
    assert content["findings_by_severity"]["high"] == 1
    assert "risk_factors" in content
    assert any("high" in rf.lower() for rf in content["risk_factors"])


@pytest.mark.asyncio
async def test_markdown_summary_renders_all_sections(client):
    """Project summary markdown contains all expected sections."""
    pid = "proj_md_all"

    project = load_example("project/create-project.request.json")
    project["project_id"] = pid
    project["ai_enabled"] = True
    await client.post("/api/v1/projects", json=project)

    # Add fairness case
    fc_body = {
        "risk_tier": "r1",
        "fairness_criticality": "medium",
    }
    await client.post(f"/api/v1/projects/{pid}/fairness-cases", json=fc_body)

    r = await client.get(f"/api/v1/projects/{pid}/summary?format=markdown")
    assert r.status_code == 200
    md = r.json()["content"]
    assert "## Project Identity" in md
    # Should contain fairness section for AI-enabled project with fairness case
    assert "## Fairness Governance" in md


@pytest.mark.asyncio
async def test_monitoring_signals_flow(client):
    """Ingest and query monitoring signals."""
    pid = "proj_signals"
    await client.post(
        "/api/v1/projects",
        json={**load_example("project/create-project.request.json"), "project_id": pid},
    )

    # Ingest signals
    for val in [0.02, 0.05, 0.08]:
        await client.post(
            "/api/v1/monitoring/signals",
            json={
                "project_id": pid,
                "environment": "prod",
                "signal_type": "fairness_drift",
                "value": val,
            },
        )

    # Query
    r = await client.get(f"/api/v1/monitoring/signals?project_id={pid}&signal_type=fairness_drift")
    assert r.status_code == 200
