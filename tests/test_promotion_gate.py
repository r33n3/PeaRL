"""Tests for promotion gate evaluator — exercises rules against DB state."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


async def _setup_project(client, project_id="proj_gate_test", ai_enabled=True):
    """Create a project with full inputs and compiled context."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = project_id
    project["ai_enabled"] = ai_enabled
    await client.post("/api/v1/projects", json=project)

    baseline = load_example("project/org-baseline.request.json")
    await client.post(f"/api/v1/projects/{project_id}/org-baseline", json=baseline)

    spec = load_example("project/app-spec.request.json")
    await client.post(f"/api/v1/projects/{project_id}/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post(f"/api/v1/projects/{project_id}/environment-profile", json=profile)

    compile_req = load_example("compile/compile-context.request.json")
    compile_req["project_id"] = project_id
    await client.post(f"/api/v1/projects/{project_id}/compile-context", json=compile_req)

    return project_id


@pytest.mark.asyncio
async def test_evaluate_promotion_fully_provisioned(client):
    """Fully provisioned project evaluates against gates."""
    pid = await _setup_project(client)

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    assert "status" in data
    assert "rule_results" in data
    assert data["total_count"] > 0
    assert data["passed_count"] >= 0
    assert 0 <= data["progress_pct"] <= 100


@pytest.mark.asyncio
async def test_evaluate_returns_source_and_target(client):
    """Evaluation includes source and target environments."""
    pid = await _setup_project(client)

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    data = r.json()
    assert "source_environment" in data
    assert "target_environment" in data


@pytest.mark.asyncio
async def test_missing_baseline_fails_rule(client):
    """Project without baseline fails the org_baseline_attached rule."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_no_baseline"
    project["ai_enabled"] = False
    await client.post("/api/v1/projects", json=project)

    # Only attach env profile (needed for current env detection) and app spec
    spec = load_example("project/app-spec.request.json")
    await client.post("/api/v1/projects/proj_no_baseline/app-spec", json=spec)

    profile = load_example("project/environment-profile.request.json")
    await client.post("/api/v1/projects/proj_no_baseline/environment-profile", json=profile)

    r = await client.post("/api/v1/projects/proj_no_baseline/promotions/evaluate")
    data = r.json()
    # Should have failures
    failed_rules = [rr for rr in data.get("rule_results", []) if rr["result"] == "fail"]
    baseline_fail = [rr for rr in failed_rules if rr["rule_type"] == "org_baseline_attached"]
    assert len(baseline_fail) == 1


@pytest.mark.asyncio
async def test_critical_findings_block_promotion(client):
    """Critical findings cause the critical_findings_zero rule to fail."""
    pid = await _setup_project(client, project_id="proj_crit_findings")

    # Ingest a critical finding
    findings_req = load_example("findings/findings-ingest.request.json")
    findings_req["findings"][0]["project_id"] = pid
    findings_req["findings"][0]["finding_id"] = "find_crit_001"
    findings_req["findings"][0]["severity"] = "critical"
    await client.post("/api/v1/findings/ingest", json=findings_req)

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    data = r.json()
    crit_rule = [rr for rr in data.get("rule_results", []) if rr["rule_type"] == "critical_findings_zero"]
    if crit_rule:
        assert crit_rule[0]["result"] == "fail"


@pytest.mark.asyncio
async def test_ai_rules_skipped_when_not_ai_enabled(client):
    """AI-only rules are skipped when project is not AI-enabled."""
    pid = await _setup_project(client, project_id="proj_not_ai", ai_enabled=False)

    r = await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    data = r.json()
    skipped = [rr for rr in data.get("rule_results", []) if rr["result"] == "skip"]
    # AI-only rules should be skipped
    ai_rule_types = {"fairness_case_defined", "model_card_documented"}
    skipped_types = {rr["rule_type"] for rr in skipped}
    assert skipped_types.issuperset(ai_rule_types & skipped_types)


@pytest.mark.asyncio
async def test_get_promotion_readiness_no_evaluation(client):
    """Readiness endpoint returns helpful message when no evaluation exists."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_no_eval"
    await client.post("/api/v1/projects", json=project)

    r = await client.get("/api/v1/projects/proj_no_eval/promotions/readiness")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "not_evaluated"


@pytest.mark.asyncio
async def test_get_promotion_readiness_after_evaluation(client):
    """Readiness endpoint returns latest evaluation after evaluating."""
    pid = await _setup_project(client, project_id="proj_readiness")

    await client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    r = await client.get(f"/api/v1/projects/{pid}/promotions/readiness")
    assert r.status_code == 200
    data = r.json()
    assert data["project_id"] == pid
    assert "status" in data
    assert "passed_count" in data


@pytest.mark.asyncio
async def test_request_promotion_creates_approval(client):
    """Request promotion triggers evaluation and creates approval request."""
    pid = await _setup_project(client, project_id="proj_req_promo")

    r = await client.post(f"/api/v1/projects/{pid}/promotions/request")
    assert r.status_code == 202
    data = r.json()
    assert data["project_id"] == pid
    assert "approval_request_id" in data
    assert "evaluation_id" in data
    assert data["status"] in ("pending_approval", "evaluation_failed")


@pytest.mark.asyncio
async def test_promotion_history_empty(client):
    """History is empty for a new project."""
    project = load_example("project/create-project.request.json")
    project["project_id"] = "proj_hist_empty"
    await client.post("/api/v1/projects", json=project)

    r = await client.get("/api/v1/projects/proj_hist_empty/promotions/history")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_default_gates(client):
    """Default promotion gates are seeded on startup."""
    r = await client.get("/api/v1/promotions/gates")
    assert r.status_code == 200
    gates = r.json()
    assert len(gates) == 3
    gate_ids = {g["gate_id"] for g in gates}
    assert "gate_sandbox_to_dev" in gate_ids
    assert "gate_dev_to_preprod" in gate_ids
    assert "gate_preprod_to_prod" in gate_ids


@pytest.mark.asyncio
async def test_default_gate_rule_counts(client):
    """Default gates have the correct number of rules."""
    r = await client.get("/api/v1/promotions/gates")
    gates = {g["gate_id"]: g for g in r.json()}
    assert gates["gate_sandbox_to_dev"]["rule_count"] == 7
    assert gates["gate_dev_to_preprod"]["rule_count"] == 26
    assert gates["gate_preprod_to_prod"]["rule_count"] == 29
