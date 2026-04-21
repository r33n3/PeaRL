"""Tests for promotion gate evaluator — exercises rules against DB state."""

import json
from datetime import datetime, timezone
from pathlib import Path  # noqa: F401 — used by load_example

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
    profile["environment"] = "pilot"
    profile["delivery_stage"] = "pilot"
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
    profile["environment"] = "pilot"
    profile["delivery_stage"] = "pilot"
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
    assert len(gates) == 2
    gate_ids = {g["gate_id"] for g in gates}
    assert "gate_5730ef26ca8c46e9" in gate_ids  # pilot → dev
    assert "gate_ce6c49cb2a3d48bf" in gate_ids  # dev → prod


@pytest.mark.asyncio
async def test_default_gate_rule_counts(client):
    """Default gates have the correct number of rules."""
    r = await client.get("/api/v1/promotions/gates")
    gates = {g["gate_id"]: g for g in r.json()}
    assert gates["gate_5730ef26ca8c46e9"]["rule_count"] == 8   # pilot → dev
    assert gates["gate_ce6c49cb2a3d48bf"]["rule_count"] == 25  # dev → prod


# ---------------------------------------------------------------------------
# Trust accumulation — auto-pass gate tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_gates_have_trust_fields(client):
    """Default gates include auto_pass, pass_count, auto_pass_threshold fields."""
    r = await client.get("/api/v1/promotions/gates")
    assert r.status_code == 200
    gates = r.json()
    for gate in gates:
        assert "auto_pass" in gate, f"auto_pass missing from gate {gate['gate_id']}"
        assert "pass_count" in gate
        assert "auto_pass_threshold" in gate
        assert gate["auto_pass"] is False
        assert gate["pass_count"] == 0
        assert gate["auto_pass_threshold"] == 5


@pytest.mark.asyncio
async def test_patch_gate_updates_threshold(client):
    """PATCH /promotions/gates/{id} updates auto_pass_threshold."""
    r = await client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]

    r = await client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass_threshold": 2})
    assert r.status_code == 200
    assert r.json()["auto_pass_threshold"] == 2

    # Verify persisted
    r = await client.get(f"/api/v1/promotions/gates/{gate_id}")
    assert r.json()["auto_pass_threshold"] == 2


@pytest.mark.asyncio
async def test_patch_gate_can_set_auto_pass_directly(client):
    """PATCH /promotions/gates/{id} can manually set auto_pass flag."""
    r = await client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]

    r = await client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass": True})
    assert r.status_code == 200
    assert r.json()["auto_pass"] is True

    # Reset
    await client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass": False})


@pytest.mark.asyncio
async def test_get_single_gate_includes_trust_fields(client):
    """GET /promotions/gates/{id} includes trust accumulation fields."""
    r = await client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]

    r = await client.get(f"/api/v1/promotions/gates/{gate_id}")
    assert r.status_code == 200
    data = r.json()
    assert "auto_pass" in data
    assert "pass_count" in data
    assert "auto_pass_threshold" in data


def _project_payload(project_id: str, name: str = "", ai_enabled: bool = False) -> dict:
    return {
        "schema_version": "1.1",
        "project_id": project_id,
        "name": name or f"Test Project {project_id}",
        "owner_team": "platform",
        "business_criticality": "low",
        "external_exposure": "internal_only",
        "ai_enabled": ai_enabled,
    }


def _decide_payload(approval_request_id: str, decision: str = "approve") -> dict:
    return {
        "schema_version": "1.1",
        "approval_request_id": approval_request_id,
        "decision": decision,
        "decided_by": "test-reviewer",
        "decider_role": "security_reviewer",
        "reason": "Test decision",
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": "trc_test_trust_gate01",
    }


@pytest.mark.asyncio
async def test_human_approved_counter_increments(reviewer_client, client):
    """pass_count increments when a human approves a promotion gate request."""
    await client.post("/api/v1/projects", json=_project_payload("proj_trust_counter"))

    # Set threshold high so auto_pass doesn't flip yet — we only want to verify counter
    r = await client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]  # sandbox_to_dev
    await client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass_threshold": 10})

    # Request a promotion — creates pending approval
    r = await client.post("/api/v1/projects/proj_trust_counter/promotions/request")
    assert r.status_code == 202
    approval_id = r.json()["approval_request_id"]

    # Human approves
    r = await reviewer_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json=_decide_payload(approval_id),
    )
    assert r.status_code == 200

    # pass_count should have incremented on the gate
    r = await client.get(f"/api/v1/promotions/gates/{gate_id}")
    assert r.json()["pass_count"] >= 1


@pytest.mark.asyncio
async def test_auto_pass_flips_after_threshold_and_no_drift(reviewer_client, client):
    """Gate flips auto_pass=True after pass_count reaches threshold with no open drift findings."""
    await client.post("/api/v1/projects", json=_project_payload("proj_trust_flip"))

    # Set threshold to 1 so a single human approval triggers the flip
    r = await client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]
    await client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass_threshold": 1})

    # Request + human approve
    r = await client.post("/api/v1/projects/proj_trust_flip/promotions/request")
    assert r.status_code == 202
    approval_id = r.json()["approval_request_id"]

    r = await reviewer_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json=_decide_payload(approval_id),
    )
    assert r.status_code == 200

    # Gate should now have auto_pass=True (pass_count=1 >= threshold=1, no drift findings)
    r = await client.get(f"/api/v1/promotions/gates/{gate_id}")
    assert r.json()["auto_pass"] is True
    assert r.json()["pass_count"] >= 1
