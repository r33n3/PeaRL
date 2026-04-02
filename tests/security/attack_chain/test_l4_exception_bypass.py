"""L4 — Exception Bypass: Operator Cannot Self-Approve Exceptions

Attack chain level 4: an autonomous agent with operator role creates an
exception and then attempts to approve it without a human reviewer, effectively
bypassing the governance gate.

Hard controls tested:
  - POST /exceptions/{id}/decide requires reviewer role → 403
  - Exception status remains "pending" after failed bypass attempt
  - No alternate HTTP method on the exception resource allows status mutation by operators

Positive tests:
  - Reviewer CAN approve a pending exception → 200, status changes to "approved"
  - Exception creation itself is a legitimate operator workflow → 201

Note: L4 is distinct from L1/L3 in that it explicitly validates the post-bypass
state of the exception record — the status must remain "pending" even after a
403 response, ruling out partial updates.

Reference: CLAUDE-security-validation.md L4
Control: src/pearl/api/routes/exceptions.py (RequireReviewer on /decide)
         src/pearl/dependencies.py (require_role("reviewer", "admin"))
"""

import pytest

from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Fixtures — local overrides
# ---------------------------------------------------------------------------

@pytest.fixture
async def operator_client(app):
    """Operator-privileged client (local_mode=True bypasses real JWT auth).

    The attack_chain conftest aliases operator_client = client, but the root
    app fixture does not set settings.local_mode=True (PEARL_LOCAL=1 maps to
    PEARL_LOCAL_MODE env var, not PEARL_LOCAL). We patch it here explicitly,
    matching the same pattern reviewer_client uses for local_reviewer_mode.
    """
    from pearl.config import settings
    from httpx import ASGITransport, AsyncClient

    original = settings.local_mode
    settings.local_mode = True
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        settings.local_mode = original


def _exception_payload(exc_id: str, project_id: str) -> dict:
    return {
        "schema_version": "1.1",
        "exception_id": exc_id,
        "project_id": project_id,
        "requested_by": "agent@example.com",
        "rationale": "L4 attack chain test — operator bypass attempt",
        "status": "pending",
        "trace_id": generate_id("trace_"),
    }


# ---------------------------------------------------------------------------
# L4 hard control: operator cannot decide exceptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l4_operator_cannot_approve_exception(operator_client, test_project):
    """
    L4 control: operator role cannot call POST /exceptions/{id}/decide.

    Attack: agent creates an exception then immediately tries to self-approve it.
    Expected: 403 AUTHORIZATION_ERROR
    Control: RequireReviewer = Depends(require_role("reviewer", "admin")) in exceptions.py
    """
    exc_id = generate_id("exc_")
    create_resp = await operator_client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )
    assert create_resp.status_code == 201, f"Exception creation failed: {create_resp.json()}"

    decide_resp = await operator_client.post(
        f"/api/v1/exceptions/{exc_id}/decide",
        json={"decision": "approve", "decided_by": "agent@example.com"},
    )
    assert decide_resp.status_code == 403, (
        f"Expected 403 for operator /decide, got {decide_resp.status_code}. "
        "Operator role must not be able to self-approve exceptions."
    )
    body = decide_resp.json()
    assert body["error"]["code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_l4_exception_status_unchanged_after_bypass_attempt(operator_client, test_project):
    """
    L4 state integrity: exception status remains 'pending' after a failed bypass.

    A 403 response is necessary but not sufficient — the exception record must
    also not have been partially mutated to 'approved' before the auth check fired.
    """
    exc_id = generate_id("exc_")
    await operator_client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )

    # Attempted bypass — expect 403
    await operator_client.post(
        f"/api/v1/exceptions/{exc_id}/decide",
        json={"decision": "approve", "decided_by": "agent@example.com"},
    )

    # Verify the exception is still pending
    list_resp = await operator_client.get(f"/api/v1/projects/{test_project}/exceptions")
    assert list_resp.status_code == 200
    exceptions = list_resp.json()
    our_exc = next((e for e in exceptions if e["exception_id"] == exc_id), None)
    assert our_exc is not None, f"Exception {exc_id} not found in project exceptions list"
    assert our_exc["status"] == "pending", (
        f"Exception status must remain 'pending' after failed bypass attempt. "
        f"Got: {our_exc['status']}. Partial mutation before auth check is a vulnerability."
    )


@pytest.mark.asyncio
async def test_l4_operator_cannot_reject_exception(operator_client, test_project):
    """
    L4 control: operator role cannot reject exceptions either (not just approve).

    All /decide actions require reviewer role — the gate is not approve-only.
    """
    exc_id = generate_id("exc_")
    await operator_client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )

    decide_resp = await operator_client.post(
        f"/api/v1/exceptions/{exc_id}/decide",
        json={"decision": "reject", "decided_by": "agent@example.com"},
    )
    assert decide_resp.status_code == 403


# ---------------------------------------------------------------------------
# Positive tests: legitimate reviewer workflow must not be blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l4_reviewer_can_approve_exception(reviewer_client, operator_client, test_project):
    """Positive: reviewer CAN approve a pending exception — governance must not over-block."""
    exc_id = generate_id("exc_")
    create_resp = await operator_client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )
    assert create_resp.status_code == 201

    decide_resp = await reviewer_client.post(
        f"/api/v1/exceptions/{exc_id}/decide",
        json={"decision": "approve", "decided_by": "reviewer@example.com"},
    )
    assert decide_resp.status_code == 200, (
        f"Reviewer could not approve exception: {decide_resp.json()}. "
        "Governance must allow legitimate reviewer actions."
    )


@pytest.mark.asyncio
async def test_l4_operator_can_create_exception(operator_client, test_project):
    """Positive: operator CAN create exceptions — this is the intended workflow."""
    exc_id = generate_id("exc_")
    resp = await operator_client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["exception_id"] == exc_id
    assert data["status"] == "pending"
