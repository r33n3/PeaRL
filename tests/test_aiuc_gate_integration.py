# tests/test_aiuc_gate_integration.py
"""Integration test: AIUC-1 compliance gate evaluates correctly end-to-end."""
import pytest


_BASE_PROJECT = {
    "schema_version": "1.1",
    "owner_team": "test-team",
    "business_criticality": "low",
    "external_exposure": "internal_only",
}


@pytest.mark.asyncio
async def test_aiuc_gate_fails_with_no_evidence(client):
    """New project with no framework evidence fails AIUC-1 gate."""
    r = await client.post("/api/v1/projects", json={
        **_BASE_PROJECT,
        "project_id": "proj_aiuc_noev",
        "name": "AIUC No Evidence",
        "ai_enabled": True,
    })
    assert r.status_code == 201

    r = await client.post("/api/v1/projects/proj_aiuc_noev/promotions/evaluate")
    assert r.status_code == 200
    data = r.json()

    aiuc = data.get("aiuc_compliance", {})
    assert aiuc["score_pct"] < 100.0
    assert len(aiuc["outstanding"]) > 0
    assert "hints" in aiuc

    # AIUC rule result should be in rule_results
    aiuc_rules = [rr for rr in data["rule_results"] if rr["rule_type"] == "aiuc_compliance_score"]
    assert len(aiuc_rules) == 1
    assert aiuc_rules[0]["result"] == "fail"


@pytest.mark.asyncio
async def test_aiuc_compliance_endpoint(client):
    """GET /promotions/aiuc-compliance returns structured response."""
    await client.post("/api/v1/projects", json={
        **_BASE_PROJECT,
        "project_id": "proj_aiuc_ep",
        "name": "AIUC Endpoint Test",
        "ai_enabled": True,
    })

    r = await client.get("/api/v1/projects/proj_aiuc_ep/promotions/aiuc-compliance")
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == "proj_aiuc_ep"
    assert "score_pct" in data
    assert "outstanding" in data
    assert "hints" in data
    assert "mandatory_controls" in data
    assert len(data["mandatory_controls"]) >= 15


@pytest.mark.asyncio
async def test_aiuc_gate_skipped_when_not_ai_enabled(client):
    """AIUC gate is ai_only=True — skipped for non-AI projects."""
    await client.post("/api/v1/projects", json={
        **_BASE_PROJECT,
        "project_id": "proj_aiuc_skip",
        "name": "Non-AI",
        "ai_enabled": False,
    })

    r = await client.post("/api/v1/projects/proj_aiuc_skip/promotions/evaluate")
    assert r.status_code == 200
    aiuc_rules = [
        rr for rr in r.json()["rule_results"]
        if rr["rule_type"] == "aiuc_compliance_score"
    ]
    # ai_only rules are skipped for non-AI projects
    assert all(rr["result"] == "skip" for rr in aiuc_rules)


@pytest.mark.asyncio
async def test_aiuc_evidence_satisfies_controls(client):
    """Submitting framework evidence reduces outstanding AIUC-1 controls."""
    await client.post("/api/v1/projects", json={
        **_BASE_PROJECT,
        "project_id": "proj_aiuc_ev",
        "name": "AIUC Evidence",
        "ai_enabled": True,
    })

    # Submit evidence for owasp_llm/llm01 — should satisfy B005.1 and B005.2
    await client.post("/api/v1/projects/proj_aiuc_ev/evidence", json={
        "environment": "pilot",
        "evidence_type": "attestation",
        "evidence_data": {
            "control_id": "owasp_llm/llm01_prompt_injection",
            "findings": "Input filtering implemented via LiteLLM guardrails",
            "artifact_refs": ["src/middleware/input_filter.py"],
        },
    })

    r = await client.get("/api/v1/projects/proj_aiuc_ev/promotions/aiuc-compliance")
    data = r.json()
    assert "B005.1" not in data["outstanding"]
    assert "B005.2" not in data["outstanding"]
