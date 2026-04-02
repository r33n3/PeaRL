"""Integration tests for server-authoritative audit trail."""

import pytest

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
    import hashlib
    import hmac as _hmac
    from pearl.config import settings
    expected_payload = (
        f"{event_id}:"
        f"{resource_id}:"
        f"test.event:"
        f"usr_tester:"
        f"{evt.timestamp.isoformat()}"
    )
    expected_sig = _hmac.new(
        settings.audit_hmac_key.encode(),
        expected_payload.encode(),
        hashlib.sha256,
    ).hexdigest()
    assert evt.signature == expected_sig, f"HMAC signature mismatch: {evt.signature!r} != {expected_sig!r}"
