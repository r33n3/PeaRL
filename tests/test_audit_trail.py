"""Integration tests for server-authoritative audit trail."""

import hashlib
import hmac as _hmac

import pytest

from pearl.config import settings
from pearl.repositories.fairness_repo import AuditEventRepository
from pearl.services.id_generator import generate_id


@pytest.mark.asyncio
async def test_append_stores_hmac_signature(db_session):
    """AuditEventRepository.append() must store a non-null HMAC signature."""
    event_id = generate_id("evt_")
    resource_id = "proj_test001"
    await AuditEventRepository(db_session).append(
        event_id=event_id,
        resource_id=resource_id,
        action_type="test.event",
        actor="usr_tester",
        details={"note": "hmac test"},
    )
    await db_session.commit()

    events = await AuditEventRepository(db_session).list_by_resource(resource_id)
    assert len(events) == 1
    evt = events[0]
    assert evt.signature is not None, "signature must be stored"
    assert len(evt.signature) == 64, "HMAC-SHA256 hex digest is 64 chars"

    # Independently verify the HMAC value is correct
    # Use naive timestamp (tz stripped) to match the canonical form append() uses
    ts = evt.timestamp.replace(tzinfo=None)
    expected_payload = (
        f"{event_id}:"
        f"{resource_id}:"
        f"test.event:"
        f"usr_tester:"
        f"{ts.isoformat()}"
    )
    expected_sig = _hmac.new(
        settings.audit_hmac_key.encode(),
        expected_payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert evt.signature == expected_sig, f"HMAC signature mismatch"


@pytest.mark.asyncio
async def test_decide_approval_writes_audit_event(reviewer_client):
    """POST /approvals/{id}/decide writes an audit_events row with action_type approval.decided."""
    appr_id = "appr_aud_test001"
    r = await reviewer_client.post("/api/v1/approvals/requests", json={
        "schema_version": "1.0",
        "approval_request_id": appr_id,
        "project_id": "proj_aud_appr01",
        "environment": "dev",
        "request_type": "deployment_gate",
        "trigger": "manual",
        "requested_by": "usr_tester",
        "status": "pending",
        "created_at": "2026-04-01T00:00:00Z",
        "trace_id": "trace-audit-test-001",
    })
    assert r.status_code == 201

    r = await reviewer_client.post(f"/api/v1/approvals/{appr_id}/decide", json={
        "schema_version": "1.0",
        "approval_request_id": appr_id,
        "decision": "approve",
        "decided_by": "usr_reviewer",
        "decider_role": "reviewer",
        "reason": "looks good",
        "decided_at": "2026-04-01T00:01:00Z",
        "trace_id": "trace-audit-test-002",
    })
    assert r.status_code == 200

    r = await reviewer_client.get(f"/api/v1/audit/events?resource_id={appr_id}")
    assert r.status_code == 200
    events = r.json()
    action_types = [e["action_type"] for e in events]
    assert "approval.decided" in action_types, f"Expected approval.decided in {action_types}"


@pytest.mark.asyncio
async def test_create_exception_writes_audit_event(reviewer_client):
    """POST /exceptions writes an audit_events row with action_type exception.created."""
    exc_id = "exc_aud_test001"
    r = await reviewer_client.post("/api/v1/exceptions", json={
        "schema_version": "1.0",
        "exception_id": exc_id,
        "project_id": "proj_aud_exc01",
        "scope": {"controls": ["no_critical_findings"], "environment": "sandbox"},
        "status": "pending",
        "requested_by": "usr_tester",
        "rationale": "audit trail test",
        "trace_id": "trace-exc-audit-001",
    })
    assert r.status_code == 201

    r = await reviewer_client.get(f"/api/v1/audit/events?resource_id={exc_id}")
    assert r.status_code == 200
    events = r.json()
    action_types = [e["action_type"] for e in events]
    assert "exception.created" in action_types, f"Expected exception.created in {action_types}"


@pytest.mark.asyncio
async def test_gate_evaluated_writes_audit_event(reviewer_client):
    """POST /projects/{id}/promotions/evaluate writes an audit_events row with action_type gate.evaluated."""
    pid = "proj_aud_gate01"
    r = await reviewer_client.post("/api/v1/projects", json={
        "schema_version": "1.0",
        "project_id": pid,
        "name": "Gate Audit Test",
        "owner_team": "audit-team",
        "business_criticality": "low",
        "external_exposure": "internal_only",
        "ai_enabled": False,
    })
    assert r.status_code == 201

    r = await reviewer_client.post(f"/api/v1/projects/{pid}/promotions/evaluate")
    assert r.status_code == 200
    gate_id = r.json().get("gate_id")
    assert gate_id, "evaluation must return a gate_id"

    r = await reviewer_client.get(f"/api/v1/audit/events?resource_id={gate_id}")
    assert r.status_code == 200
    events = r.json()
    action_types = [e["action_type"] for e in events]
    assert "gate.evaluated" in action_types, f"Expected gate.evaluated in {action_types}"


@pytest.mark.asyncio
async def test_promotion_requested_writes_audit_event(reviewer_client):
    """POST /projects/{id}/promotions/request writes an audit_events row with action_type promotion.requested."""
    pid = "proj_aud_prom01"
    r = await reviewer_client.post("/api/v1/projects", json={
        "project_id": pid,
        "name": "Promotion Audit Test",
        "owner_team": "platform",
        "business_criticality": "low",
        "external_exposure": "internal_only",
        "ai_enabled": False,
        "schema_version": "1.0",
    })
    assert r.status_code == 201

    r = await reviewer_client.post(f"/api/v1/projects/{pid}/promotions/request")
    assert r.status_code == 202
    approval_id = r.json().get("approval_request_id")
    assert approval_id

    r = await reviewer_client.get(f"/api/v1/audit/events?resource_id={approval_id}")
    assert r.status_code == 200
    events = r.json()
    action_types = [e["action_type"] for e in events]
    assert "promotion.requested" in action_types, f"Expected promotion.requested in {action_types}"


@pytest.mark.asyncio
async def test_audit_events_requires_auth(app):
    """GET /audit/events returns 401 when called without authentication."""
    from httpx import ASGITransport, AsyncClient
    from pearl.config import settings

    original_local = settings.local_mode
    original_reviewer = settings.local_reviewer_mode
    settings.local_mode = False
    settings.local_reviewer_mode = False
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            r = await ac.get("/api/v1/audit/events?resource_id=proj_test")
            assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"
    finally:
        settings.local_mode = original_local
        settings.local_reviewer_mode = original_reviewer


@pytest.mark.asyncio
async def test_audit_events_returns_hmac_valid(reviewer_client):
    """GET /audit/events includes hmac_valid per event."""
    # Create an exception to generate an audit event via the exception.created write
    exc_id = "exc_hmac_test002"
    r = await reviewer_client.post("/api/v1/exceptions", json={
        "exception_id": exc_id,
        "project_id": "proj_hmac_verify",
        "scope": {"controls": ["test"], "environment": "sandbox"},
        "status": "pending",
        "requested_by": "usr_tester",
        "rationale": "hmac verify test",
        "schema_version": "1.0",
        "trace_id": "trace_hmac_test",
    })
    assert r.status_code == 201

    r = await reviewer_client.get(f"/api/v1/audit/events?resource_id={exc_id}")
    assert r.status_code == 200
    events = r.json()
    assert len(events) > 0, "Expected at least one audit event"
    for evt in events:
        assert "hmac_valid" in evt, f"hmac_valid missing from event: {evt}"
        assert evt["hmac_valid"] is True, f"Expected hmac_valid=True, got False for event: {evt}"
