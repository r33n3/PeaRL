"""Tests for fairness governance API routes."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _create_project(client, project_id="proj_fairness_test"):
    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    project["ai_enabled"] = True
    await client.post("/api/v1/projects", json=project)
    return project_id


@pytest.mark.asyncio
async def test_create_fairness_case(client):
    """Create a fairness case for a project."""
    pid = await _create_project(client)
    body = {
        "risk_tier": "r2",
        "fairness_criticality": "high",
        "system_description": "AI customer support chatbot",
        "stakeholders": ["customers", "agents"],
        "fairness_principles": ["equal_treatment"],
    }
    r = await client.post(f"/api/v1/projects/{pid}/fairness-cases", json=body)
    assert r.status_code == 201
    data = r.json()
    assert data["project_id"] == pid
    assert "fc_id" in data


@pytest.mark.asyncio
async def test_list_fairness_cases(client):
    """List fairness cases for a project."""
    pid = await _create_project(client, "proj_fc_list")
    body = {
        "risk_tier": "r1",
        "fairness_criticality": "medium",
    }
    await client.post(f"/api/v1/projects/{pid}/fairness-cases", json=body)

    r = await client.get(f"/api/v1/projects/{pid}/fairness-cases")
    assert r.status_code == 200
    cases = r.json()
    assert len(cases) >= 1


@pytest.mark.asyncio
async def test_create_fairness_requirements(client):
    """Create fairness requirements spec for a project."""
    pid = await _create_project(client, "proj_frs")
    body = {
        "requirements": [
            {
                "requirement_id": "fr_001",
                "statement": "No demographic bias in recommendations",
                "requirement_type": "prohibit",
            },
            {
                "requirement_id": "fr_002",
                "statement": "Equal opportunity score >= 0.8",
                "requirement_type": "threshold",
                "threshold_value": 0.8,
            },
        ],
        "version": "1.0",
    }
    r = await client.post(f"/api/v1/projects/{pid}/fairness-requirements", json=body)
    assert r.status_code == 201
    data = r.json()
    assert "frs_id" in data


@pytest.mark.asyncio
async def test_get_fairness_requirements(client):
    """Get fairness requirements for a project."""
    pid = await _create_project(client, "proj_frs_get")
    body = {
        "requirements": [
            {
                "requirement_id": "fr_001",
                "statement": "Test requirement",
                "requirement_type": "require",
            }
        ],
    }
    await client.post(f"/api/v1/projects/{pid}/fairness-requirements", json=body)

    r = await client.get(f"/api/v1/projects/{pid}/fairness-requirements")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_submit_evidence(client):
    """Submit evidence package for a project."""
    pid = await _create_project(client, "proj_evidence")
    body = {
        "environment": "dev",
        "evidence_type": "bias_benchmark",
        "summary": "Bias benchmark results across protected groups",
        "evidence_data": {"metrics": {"demographic_parity": 0.92}},
    }
    r = await client.post(f"/api/v1/projects/{pid}/evidence", json=body)
    assert r.status_code == 201
    data = r.json()
    assert "evidence_id" in data


@pytest.mark.asyncio
async def test_list_evidence(client):
    """List evidence packages for a project."""
    pid = await _create_project(client, "proj_ev_list")
    body = {
        "environment": "dev",
        "evidence_type": "bias_benchmark",
        "summary": "Test evidence",
    }
    await client.post(f"/api/v1/projects/{pid}/evidence", json=body)

    r = await client.get(f"/api/v1/projects/{pid}/evidence")
    assert r.status_code == 200
    evidence = r.json()
    assert len(evidence) >= 1


@pytest.mark.asyncio
async def test_sign_attestation(client):
    """Sign attestation on an evidence package."""
    pid = await _create_project(client, "proj_attest")
    body = {
        "environment": "dev",
        "evidence_type": "fairness_audit",
        "summary": "Fairness audit results",
    }
    r = await client.post(f"/api/v1/projects/{pid}/evidence", json=body)
    ev_id = r.json()["evidence_id"]

    sign_body = {"signed_by": "reviewer@example.com"}
    r = await client.post(f"/api/v1/projects/{pid}/evidence/{ev_id}/sign", json=sign_body)
    assert r.status_code == 200
    data = r.json()
    assert data["attestation_status"] == "signed"


@pytest.mark.asyncio
async def test_create_fairness_exception(client):
    """Create a fairness exception with compensating controls."""
    pid = await _create_project(client, "proj_fex")
    body = {
        "requirement_id": "fr_001",
        "rationale": "Cannot meet threshold due to data scarcity in edge cases",
        "compensating_controls": ["manual_review", "quarterly_audit"],
    }
    r = await client.post(f"/api/v1/projects/{pid}/fairness-exceptions", json=body)
    assert r.status_code == 201
    data = r.json()
    assert "exception_id" in data


@pytest.mark.asyncio
async def test_ingest_monitoring_signal(client):
    """Ingest a runtime fairness monitoring signal."""
    body = {
        "project_id": "proj_fairness_test",
        "environment": "prod",
        "signal_type": "fairness_drift",
        "value": 0.05,
        "threshold": 0.1,
        "metadata": {"metric": "demographic_parity_diff"},
    }
    # Create project first
    await _create_project(client)

    r = await client.post("/api/v1/monitoring/signals", json=body)
    assert r.status_code == 201
    data = r.json()
    assert "signal_id" in data


@pytest.mark.asyncio
async def test_query_monitoring_signals(client):
    """Query monitoring signals for a project."""
    pid = await _create_project(client, "proj_sig_query")
    body = {
        "project_id": pid,
        "environment": "prod",
        "signal_type": "fairness_drift",
        "value": 0.03,
    }
    await client.post("/api/v1/monitoring/signals", json=body)

    r = await client.get(f"/api/v1/monitoring/signals?project_id={pid}&signal_type=fairness_drift")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_submit_context_receipt(client):
    """Submit a context receipt proving agent consumed fairness context."""
    body = {
        "project_id": "proj_fairness_test",
        "commit_hash": "abc123def456",
        "agent_id": "claude-code",
        "tool_calls": ["read_fairness_case", "read_evidence"],
        "artifact_hashes": {"fairness_case": "sha256:abc123"},
    }
    await _create_project(client)

    r = await client.post("/api/v1/context/receipts", json=body)
    assert r.status_code == 201
    data = r.json()
    assert "cr_id" in data
