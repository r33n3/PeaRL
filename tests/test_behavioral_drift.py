"""Tests for behavioral drift finding signal path and trust accumulation auto-pass."""

from datetime import datetime, timezone

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _project_payload(project_id: str) -> dict:
    return {
        "schema_version": "1.1",
        "project_id": project_id,
        "name": f"Test Project {project_id}",
        "owner_team": "platform",
        "business_criticality": "low",
        "external_exposure": "internal_only",
        "ai_enabled": True,
    }


def _drift_finding(
    finding_id: str,
    project_id: str,
    category: str = "drift_trend",
    severity: str = "high",
) -> dict:
    """Build a minimal behavioral drift finding payload."""
    return {
        "finding_id": finding_id,
        "project_id": project_id,
        "environment": "sandbox",
        "category": category,
        "severity": severity,
        "title": f"Behavioral drift ({category})",
        "source": {
            "tool_name": "control-plane-coordinator",
            "tool_type": "behavioral_drift",
            "trust_label": "trusted_internal",
        },
        "schema_version": "1.1",
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }


def _ingest_payload(finding: dict) -> dict:
    """Wrap a finding in a minimal ingest request."""
    return {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": f"batch_{finding['finding_id']}",
            "source_system": "control-plane-coordinator",
            "connector_version": "1.0.0",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "trust_label": "trusted_internal",
        },
        "findings": [finding],
        "options": {
            "normalize_on_ingest": False,
            "strict_validation": True,
            "quarantine_on_error": False,
        },
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
        "trace_id": "trc_test_trust_001a",
    }


# ---------------------------------------------------------------------------
# Behavioral drift finding creation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_behavioral_drift_source_accepted(reviewer_client):
    """`behavioral_drift` is accepted as a valid tool_type in source."""
    await reviewer_client.post("/api/v1/projects", json=_project_payload("proj_drift_src"))
    finding = _drift_finding("find_drift_src_001", "proj_drift_src", category="drift_trend")
    r = await reviewer_client.post("/api/v1/findings/ingest", json=_ingest_payload(finding))
    assert r.status_code in (200, 201, 202), r.text
    data = r.json()
    assert data["accepted_count"] == 1


@pytest.mark.asyncio
async def test_drift_trend_category_accepted(reviewer_client):
    """`drift_trend` is accepted as a valid finding category."""
    await reviewer_client.post("/api/v1/projects", json=_project_payload("proj_drift_trend_cat"))
    finding = _drift_finding("find_drift_trend_cat_001", "proj_drift_trend_cat", category="drift_trend")
    r = await reviewer_client.post("/api/v1/findings/ingest", json=_ingest_payload(finding))
    assert r.status_code in (200, 201, 202), r.text
    assert r.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_drift_acute_category_accepted(reviewer_client):
    """`drift_acute` is accepted as a valid finding category."""
    await reviewer_client.post("/api/v1/projects", json=_project_payload("proj_drift_acute_cat"))
    finding = _drift_finding(
        "find_drift_acute_cat_001", "proj_drift_acute_cat",
        category="drift_acute", severity="high",
    )
    r = await reviewer_client.post("/api/v1/findings/ingest", json=_ingest_payload(finding))
    assert r.status_code in (200, 201, 202), r.text
    assert r.json()["accepted_count"] == 1


@pytest.mark.asyncio
async def test_drift_finding_queryable_by_category(reviewer_client):
    """Drift findings are queryable via GET /projects/{id}/findings?category=drift_trend."""
    await reviewer_client.post("/api/v1/projects", json=_project_payload("proj_drift_query"))
    finding = _drift_finding("find_drift_query_001", "proj_drift_query", category="drift_trend")
    await reviewer_client.post("/api/v1/findings/ingest", json=_ingest_payload(finding))

    r = await reviewer_client.get("/api/v1/projects/proj_drift_query/findings?category=drift_trend")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    categories = [f["category"] for f in data["items"]]
    assert "drift_trend" in categories


# ---------------------------------------------------------------------------
# Gate auto-pass trust accumulation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_default_gates_have_trust_accumulation_fields(client):
    """Default gates expose auto_pass, pass_count, auto_pass_threshold."""
    r = await client.get("/api/v1/promotions/gates")
    assert r.status_code == 200
    gates = r.json()
    assert len(gates) > 0
    for gate in gates:
        assert "auto_pass" in gate
        assert "pass_count" in gate
        assert "auto_pass_threshold" in gate
        assert gate["auto_pass"] is False
        assert gate["pass_count"] == 0
        assert gate["auto_pass_threshold"] == 5


@pytest.mark.asyncio
async def test_patch_gate_auto_pass_threshold(client):
    """PATCH /promotions/gates/{id} updates auto_pass_threshold."""
    r = await client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]

    r = await client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass_threshold": 3})
    assert r.status_code == 200
    data = r.json()
    assert data["auto_pass_threshold"] == 3
    assert data["gate_id"] == gate_id


@pytest.mark.asyncio
async def test_patch_gate_invalid_threshold_rejected(client):
    """PATCH /promotions/gates/{id} rejects non-positive threshold."""
    r = await client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]

    r = await client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass_threshold": 0})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_open_drift_trend_finding_blocks_auto_pass_flip(reviewer_client):
    """When pass_count >= threshold but open drift_trend finding exists, auto_pass stays False."""
    await reviewer_client.post("/api/v1/projects", json=_project_payload("proj_drift_blocks"))

    # Ingest a drift_trend finding
    finding = _drift_finding("find_drift_block_001", "proj_drift_blocks", category="drift_trend")
    await reviewer_client.post("/api/v1/findings/ingest", json=_ingest_payload(finding))

    # Set threshold to 1 — normally a single approval would flip auto_pass
    r = await reviewer_client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]
    await reviewer_client.patch(f"/api/v1/promotions/gates/{gate_id}", json={"auto_pass_threshold": 1})

    # Request a promotion and human-approve it
    r = await reviewer_client.post("/api/v1/projects/proj_drift_blocks/promotions/request")
    assert r.status_code == 202
    approval_id = r.json()["approval_request_id"]

    r = await reviewer_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json=_decide_payload(approval_id),
    )
    assert r.status_code == 200

    # pass_count incremented but open drift_trend finding should block auto_pass flip
    r = await reviewer_client.get(f"/api/v1/promotions/gates/{gate_id}")
    gate_data = r.json()
    assert gate_data["pass_count"] >= 1
    assert gate_data["auto_pass"] is False, "drift_trend finding should block auto_pass flip"


@pytest.mark.asyncio
async def test_resolving_drift_trend_finding_reenables_auto_pass(reviewer_client):
    """Resolving all open drift_trend findings re-enables auto_pass on eligible gates."""
    await reviewer_client.post("/api/v1/projects", json=_project_payload("proj_drift_resolve"))

    # Set gate threshold to 1 so a single approval would normally flip auto_pass
    r = await reviewer_client.get("/api/v1/promotions/gates")
    gate_id = r.json()[0]["gate_id"]
    await reviewer_client.patch(f"/api/v1/promotions/gates/{gate_id}", json={
        "auto_pass_threshold": 1,
        "auto_pass": False,
    })

    # Ingest a drift_trend finding (this will block auto_pass flip)
    finding = _drift_finding("find_drift_resolve_001", "proj_drift_resolve", category="drift_trend")
    await reviewer_client.post("/api/v1/findings/ingest", json=_ingest_payload(finding))

    # Human-approve a promotion to set pass_count=1 (threshold=1, but drift finding blocks flip)
    r = await reviewer_client.post("/api/v1/projects/proj_drift_resolve/promotions/request")
    assert r.status_code == 202
    approval_id = r.json()["approval_request_id"]
    r = await reviewer_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        json=_decide_payload(approval_id),
    )
    assert r.status_code == 200

    # Gate still has auto_pass=False due to drift finding
    r = await reviewer_client.get(f"/api/v1/promotions/gates/{gate_id}")
    assert r.json()["auto_pass"] is False

    # Find the drift_trend finding and suppress it
    r = await reviewer_client.get("/api/v1/projects/proj_drift_resolve/findings?category=drift_trend")
    assert r.json()["total"] >= 1
    finding_id = r.json()["items"][0]["finding_id"]

    r = await reviewer_client.patch(
        f"/api/v1/projects/proj_drift_resolve/findings/{finding_id}/status",
        json={"status": "suppressed"},
    )
    assert r.status_code == 200

    # Now auto_pass should be True (pass_count=1 >= threshold=1, no open drift findings)
    r = await reviewer_client.get(f"/api/v1/promotions/gates/{gate_id}")
    assert r.json()["auto_pass"] is True, "resolving drift_trend should re-enable auto_pass"


@pytest.mark.asyncio
async def test_dashboard_overview_includes_drift_trend_count(reviewer_client):
    """Dashboard project overview includes behavioral_drift_trend_count."""
    await reviewer_client.post("/api/v1/projects", json=_project_payload("proj_drift_dashboard"))

    # Initially zero
    r = await reviewer_client.get("/api/v1/dashboard/projects/proj_drift_dashboard/overview")
    assert r.status_code == 200
    data = r.json()
    assert "behavioral_drift_trend_count" in data
    assert data["behavioral_drift_trend_count"] == 0

    # Post a drift_trend finding
    finding = _drift_finding("find_drift_dash_001", "proj_drift_dashboard", category="drift_trend")
    await reviewer_client.post("/api/v1/findings/ingest", json=_ingest_payload(finding))

    r = await reviewer_client.get("/api/v1/dashboard/projects/proj_drift_dashboard/overview")
    assert r.json()["behavioral_drift_trend_count"] == 1
