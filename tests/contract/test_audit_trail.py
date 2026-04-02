"""Contract tests for the audit trail added by server-audit-trail.

Validates:
  1. Approval decisions write an audit record (action_type="approval.decided")
  2. Exception creation writes an audit record (action_type="exception.created")
  3. HMAC signature is present and valid on audit events
  4. No DELETE endpoint exists on audit events (immutability)
  5. GET /audit/events requires authentication

Tests 1, 2, 3, 5 are xfail until server-audit-trail is merged:
  - Tests 1/2: require server-audit-trail to write AuditEventRow on those actions
  - Test 3: requires server-audit-trail to add hmac_valid field to event serialisation
  - Test 5: requires server-audit-trail to add Depends(get_current_user) to /audit/events

Test 4 passes now — DELETE /audit/events/* is already absent.

action_type strings expected from server-audit-trail (see decisions.md if different):
  "approval.decided"   POST /approvals/{id}/decide
  "exception.created"  POST /exceptions
"""

from datetime import datetime, timezone

import pytest

from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _exception_payload(exc_id: str, project_id: str) -> dict:
    return {
        "schema_version": "1.1",
        "exception_id": exc_id,
        "project_id": project_id,
        "requested_by": "contract-test@example.com",
        "rationale": "Audit trail contract test",
        "status": "pending",
        "trace_id": generate_id("trace_"),
    }


def _approval_decision_payload(approval_id: str) -> dict:
    return {
        "schema_version": "1.1",
        "approval_request_id": approval_id,
        "decision": "approve",
        "decided_by": "reviewer@example.com",
        "decider_role": "reviewer",
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": generate_id("trace_"),
    }


@pytest.fixture
def strict_app(db_engine):
    """App with local_mode disabled — auth middleware enforces credentials."""
    from pearl.main import create_app
    from pearl.config import settings
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    orig_local = settings.local_mode
    orig_reviewer = settings.local_reviewer_mode
    settings.local_mode = False
    settings.local_reviewer_mode = False
    try:
        _app = create_app()
        session_factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        _app.state.db_engine = db_engine
        _app.state.db_session_factory = session_factory
        _app.state.redis = None
    finally:
        settings.local_mode = orig_local
        settings.local_reviewer_mode = orig_reviewer
    return _app


@pytest.fixture
async def strict_client(strict_app):
    """Unauthenticated client against a production-mode app."""
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=strict_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Test 1: approval decision writes audit record
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Requires server-audit-trail: POST /approvals/{id}/decide must write AuditEventRow")
async def test_approval_decision_writes_audit_record(reviewer_client, pending_approval):
    """Deciding an approval creates an audit record with action_type='approval.decided'."""
    decide_resp = await reviewer_client.post(
        f"/api/v1/approvals/{pending_approval}/decide",
        json=_approval_decision_payload(pending_approval),
    )
    assert decide_resp.status_code == 200, f"Decide failed: {decide_resp.json()}"

    audit_resp = await reviewer_client.get(
        f"/api/v1/audit/events?resource_id={pending_approval}",
    )
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    assert len(events) >= 1, "Expected at least one audit event after approval decision"

    actions = [e["action_type"] for e in events]
    assert "approval.decided" in actions, (
        f"Expected action_type='approval.decided' in audit events. Got: {actions}"
    )


# ---------------------------------------------------------------------------
# Test 2: exception creation writes audit record
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Requires server-audit-trail: POST /exceptions must write AuditEventRow")
async def test_exception_creation_writes_audit_record(client, test_project):
    """Creating an exception writes an audit record with action_type='exception.created'."""
    exc_id = generate_id("exc_")
    create_resp = await client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )
    assert create_resp.status_code == 201, f"Exception creation failed: {create_resp.json()}"

    audit_resp = await client.get(
        f"/api/v1/audit/events?resource_id={exc_id}",
    )
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    assert len(events) >= 1, "Expected at least one audit event after exception creation"

    actions = [e["action_type"] for e in events]
    assert "exception.created" in actions, (
        f"Expected action_type='exception.created' in audit events. Got: {actions}"
    )


# ---------------------------------------------------------------------------
# Test 3: HMAC signature present on audit events
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Requires server-audit-trail: audit event serialisation must include hmac_valid field")
async def test_audit_events_have_valid_hmac(client, test_project):
    """Every audit event returned by GET /audit/events must carry hmac_valid=True.

    server-audit-trail is expected to add HMAC signing to AuditEventRow.append()
    and expose hmac_valid in the /audit/events response.
    """
    # Trigger an event we know will be written (user.created is already wired)
    # by writing directly via the repository, to avoid coupling to specific routes.
    from pearl.repositories.fairness_repo import AuditEventRepository
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    session_factory = client.app.state.db_session_factory
    async with session_factory() as session:
        repo = AuditEventRepository(session)
        event_id = generate_id("evt_")
        resource_id = generate_id("res_")
        await repo.append(
            event_id=event_id,
            resource_id=resource_id,
            action_type="test.event",
            actor="contract-test",
            details={"source": "test_audit_trail.py"},
        )
        await session.commit()

    audit_resp = await client.get(f"/api/v1/audit/events?resource_id={resource_id}")
    assert audit_resp.status_code == 200
    events = audit_resp.json()
    assert len(events) >= 1, "Expected the seeded audit event to appear"

    for event in events:
        assert "hmac_valid" in event, (
            f"Audit event missing 'hmac_valid' field. "
            f"server-audit-trail must add HMAC signing to AuditEventRow. Got keys: {list(event.keys())}"
        )
        assert event["hmac_valid"] is True, (
            f"Audit event {event.get('event_id')} has hmac_valid=False — possible tampering or missing HMAC."
        )


# ---------------------------------------------------------------------------
# Test 4: no DELETE endpoint on audit events (immutability control)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_events_have_no_delete_endpoint(client):
    """DELETE /audit/events/<id> must not exist — audit records are immutable.

    405 Method Not Allowed is the expected response (route exists, method disallowed).
    404 is also acceptable (route does not exist at all).
    Either response proves the DELETE path is unavailable.
    """
    fake_event_id = generate_id("evt_")
    resp = await client.delete(f"/api/v1/audit/events/{fake_event_id}")
    assert resp.status_code in (404, 405), (
        f"Expected 404 or 405 for DELETE /audit/events/{{id}}, got {resp.status_code}. "
        "Audit events must be immutable — no delete endpoint should exist."
    )


# ---------------------------------------------------------------------------
# Test 5: GET /audit/events requires authentication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.xfail(reason="Requires server-audit-trail: /audit/events must add Depends(get_current_user)")
async def test_audit_events_require_auth(strict_client):
    """GET /audit/events without credentials must return 401.

    server-audit-trail must add an auth guard (Depends(get_current_user)) to
    the audit events endpoint. Without this, the audit trail is publicly readable,
    leaking governance decisions to unauthenticated callers.
    """
    resp = await strict_client.get("/api/v1/audit/events")
    assert resp.status_code == 401, (
        f"Expected 401 for unauthenticated access to /audit/events, got {resp.status_code}. "
        "The endpoint must enforce authentication."
    )
