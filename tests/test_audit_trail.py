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
async def test_create_exception_writes_audit_event(client):
    """POST /exceptions writes an audit_events row with action_type exception.created."""
    exc_id = "exc_aud_test001"
    r = await client.post("/api/v1/exceptions", json={
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

    r = await client.get(f"/api/v1/audit/events?resource_id={exc_id}")
    assert r.status_code == 200
    events = r.json()
    action_types = [e["action_type"] for e in events]
    assert "exception.created" in action_types, f"Expected exception.created in {action_types}"
