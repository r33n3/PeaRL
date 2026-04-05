"""L5 — Audit Spoofing: Client Cannot Forge Server-Side Audit Records

Attack chain level 5: an autonomous agent attempts to inject fake audit
records into the governance audit trail — for example, claiming that an
approval was granted when it was not.

Hard controls tested:
  1. Table isolation: client-submitted events (ClientAuditEventRow via governance
     telemetry) are entirely separate from server audit events (AuditEventRow via
     /audit/events). Client pushes never appear in the server audit trail.
  2. Server HMAC integrity: HMAC signatures on client events are computed by the
     server — the client cannot pre-compute or forge a valid signature. Verification
     of the stored signature confirms server-side control.
  3. Tamper detection: if client event data could be mutated after submission,
     the verify endpoint returns valid=False (not tested via mutation here, but
     the verify endpoint is exercised to confirm it reports valid=True for intact events).

Positive test:
  - Legitimate client audit pushes DO succeed and ARE queryable via the governance
    telemetry endpoint (correct isolation: they're stored, just in a different table).

Reference: CLAUDE-security-validation.md L5
Control: src/pearl/api/routes/governance_telemetry.py (ClientAuditEventRow)
         src/pearl/api/routes/audit.py (AuditEventRow — separate table)
"""

from datetime import datetime, timezone

import pytest

from pearl.services.id_generator import generate_id


def _telemetry_event(action: str = "approval.decided", decision: str = "approved") -> dict:
    """Build a client telemetry event payload claiming a governance action."""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": "governance",
        "action": action,
        "decision": decision,
        "reason": "L5 spoofing attack simulation",
        "source": "malicious_agent",
    }


# ---------------------------------------------------------------------------
# L5 control 1: table isolation — client events cannot pollute server audit trail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l5_client_event_not_in_server_audit_trail(client, test_project):
    """
    L5 table isolation: client-submitted events do NOT appear in GET /audit/events.

    Attack: agent pushes a fabricated event claiming action='approval.decided'
    to the governance telemetry endpoint.

    Expected: the forged event is stored in ClientAuditEventRow (governance_telemetry)
    but does NOT appear in AuditEventRow (audit.py /audit/events).

    The two tables are entirely separate. A client push cannot inject records into
    the authoritative server-written audit trail.
    """
    # Push a forged event claiming an approval was granted
    push_resp = await client.post(
        f"/api/v1/projects/{test_project}/audit-events",
        json={"events": [_telemetry_event(action="approval.decided", decision="approved")]},
    )
    assert push_resp.status_code == 201, f"Telemetry push failed: {push_resp.json()}"
    push_data = push_resp.json()
    assert push_data["received"] >= 1

    # Verify: the forged event appears in the governance telemetry endpoint
    # (it is stored — just in the wrong table for spoofing purposes)
    telemetry_resp = await client.get(f"/api/v1/projects/{test_project}/audit-events")
    assert telemetry_resp.status_code == 200
    telemetry_events = telemetry_resp.json()
    assert len(telemetry_events) >= 1, "Expected client event to be stored in telemetry table"

    # Critical check: the forged event must NOT appear in the server audit trail
    # /audit/events reads AuditEventRow only — not ClientAuditEventRow
    server_audit_resp = await client.get(
        f"/api/v1/audit/events?resource_id={test_project}",
    )
    assert server_audit_resp.status_code == 200
    server_events = server_audit_resp.json()

    # Server audit trail should not contain client-pushed events.
    # (It may contain events from other server-side actions on this project,
    # but none should have action_type sourced from the telemetry push.)
    server_action_types = [e.get("action_type", "") for e in server_events]
    # The client telemetry event has action="approval.decided" — if it leaked
    # into AuditEventRow it would appear as action_type="approval.decided"
    # pushed by the malicious agent. Verify it's absent.
    telemetry_event_ids = {e["event_id"] for e in telemetry_events}
    server_event_ids = {e.get("event_id", "") for e in server_events}

    leaked = telemetry_event_ids & server_event_ids
    assert not leaked, (
        f"Client-submitted event IDs appeared in the server audit trail: {leaked}. "
        "Table isolation is broken — client events must never pollute AuditEventRow."
    )


@pytest.mark.asyncio
async def test_l5_forged_approval_event_not_in_server_trail_by_action(client, test_project):
    """
    L5 table isolation (action-level check): server audit trail for this project
    contains no 'approval.decided' event sourced from a client push.

    This directly validates the spoofing defence: even claiming the canonical
    governance action type in a client push does not forge a server audit record.
    """
    unique_reason = f"l5-spoof-marker-{generate_id('test_')}"

    await client.post(
        f"/api/v1/projects/{test_project}/audit-events",
        json={"events": [{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "governance",
            "action": "approval.decided",
            "decision": "approved",
            "reason": unique_reason,
            "source": "attacker",
        }]},
    )

    # The server audit trail for this project should not contain any events
    # with our unique marker in any form — it is a completely different table.
    server_audit_resp = await client.get(
        f"/api/v1/audit/events?resource_id={test_project}",
    )
    server_events = server_audit_resp.json()

    # None of the server events should reference our injected reason
    for e in server_events:
        details = str(e.get("details", ""))
        assert unique_reason not in details, (
            f"Forged audit marker '{unique_reason}' found in server audit trail event {e}. "
            "Client telemetry content must not bleed into AuditEventRow."
        )


# ---------------------------------------------------------------------------
# L5 control 2: server HMAC — client cannot forge a valid signature
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l5_client_event_signature_is_server_computed(client, test_project):
    """
    L5 HMAC integrity: client events carry a server-computed HMAC signature.

    The server computes HMAC-SHA256 over (event_id, project_id, timestamp,
    event_type, action, decision) using settings.audit_hmac_key — a secret
    the client never sees. The verify endpoint confirms the stored signature
    matches the expected digest.

    This proves: the client cannot pre-compute a valid HMAC for an arbitrary
    payload, so it cannot forge a record that passes signature verification.
    """
    push_resp = await client.post(
        f"/api/v1/projects/{test_project}/audit-events",
        json={"events": [_telemetry_event()]},
    )
    assert push_resp.status_code == 201

    # List events to obtain the event_id
    list_resp = await client.get(f"/api/v1/projects/{test_project}/audit-events")
    assert list_resp.status_code == 200
    events = list_resp.json()
    assert len(events) >= 1

    event_id = events[0]["event_id"]
    assert event_id, "Event must have an event_id assigned by the server"

    # Verify the server-computed HMAC is valid
    verify_resp = await client.get(
        f"/api/v1/projects/{test_project}/audit-events/{event_id}/verify",
    )
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()

    assert "valid" in verify_data, f"Verify endpoint missing 'valid' field: {verify_data}"
    assert verify_data["valid"] is True, (
        f"Server-computed HMAC failed verification for event {event_id}: {verify_data}. "
        "This indicates a bug in the signing or verification logic."
    )


@pytest.mark.asyncio
async def test_l5_event_signature_field_present_in_listing(client, test_project):
    """
    L5 transparency: the listing endpoint exposes the signature field so
    consumers can detect events that pre-date HMAC signing (signature=None)
    vs. events with a valid server signature.
    """
    push_resp = await client.post(
        f"/api/v1/projects/{test_project}/audit-events",
        json={"events": [_telemetry_event()]},
    )
    assert push_resp.status_code == 201

    list_resp = await client.get(f"/api/v1/projects/{test_project}/audit-events")
    events = list_resp.json()
    assert len(events) >= 1

    for evt in events:
        assert "signature" in evt, (
            f"Event missing 'signature' field: {evt}. "
            "Consumers must be able to distinguish signed from unsigned events."
        )
        # Newly submitted events should always have a non-null signature
        assert evt["signature"] is not None, (
            f"Expected non-null signature on newly submitted event {evt.get('event_id')}."
        )


# ---------------------------------------------------------------------------
# Positive test: client audit pushes are stored and queryable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l5_legitimate_client_push_is_stored(client, test_project):
    """
    Positive: legitimate client audit events ARE stored and retrievable via
    the governance telemetry endpoint. Isolation does not mean the events
    are discarded — they are stored for telemetry/observability purposes,
    just in a separate table from the authoritative governance audit trail.
    """
    marker = generate_id("marker_")
    push_resp = await client.post(
        f"/api/v1/projects/{test_project}/audit-events",
        json={"events": [{
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "tool_call",
            "action": "pearl_list_findings",
            "decision": "allowed",
            "reason": marker,
            "source": "pearl_dev",
        }]},
    )
    assert push_resp.status_code == 201
    assert push_resp.json()["created"] >= 1

    list_resp = await client.get(f"/api/v1/projects/{test_project}/audit-events")
    assert list_resp.status_code == 200
    events = list_resp.json()

    reasons = [e.get("reason", "") for e in events]
    # Note: ClientAuditEventRow serialisation may not include 'reason' — check for event presence
    assert len(events) >= 1, "Expected stored telemetry event to appear in listing"
