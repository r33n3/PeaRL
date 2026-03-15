"""L3 — Direct API Exploitation: RequireReviewer Gates

Attack chain level 3: having discovered the governance endpoint schemas
(L2), an autonomous agent with operator role calls them directly — without
going through MCP tooling that enforces the developer profile.

Hard controls tested:
  - POST /approvals/{id}/decide requires reviewer role → 403
  - POST /exceptions/{id}/decide requires reviewer role → 403

Positive tests (governance must not over-block):
  - Reviewer CAN call /exceptions/{id}/decide → 200
  - Both blocks emit governance_access_denied structured log (via handlers.py)

Reference: pearl_autonomous_attack_research.md L3
Control file: src/pearl/dependencies.py (RequireReviewer = Depends(require_role(*REVIEWER_ROLES)))
"""

import logging
from datetime import datetime, timezone

import pytest

from pearl.services.id_generator import generate_id


def _exception_payload(exc_id: str, project_id: str) -> dict:
    return {
        "schema_version": "1.1",
        "exception_id": exc_id,
        "project_id": project_id,
        "requested_by": "agent@example.com",
        "rationale": "L3 test exception",
        "status": "pending",
        "trace_id": generate_id("trace_"),
    }


def _approval_decision_payload(approval_id: str, decision: str = "approve") -> dict:
    return {
        "schema_version": "1.1",
        "approval_request_id": approval_id,
        "decision": decision,
        "decided_by": "attacker@example.com",
        "decider_role": "reviewer",
        "decided_at": datetime.now(timezone.utc).isoformat(),
        "trace_id": generate_id("trace_"),
    }


# ---------------------------------------------------------------------------
# L3 hard controls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l3_operator_cannot_decide_approval(operator_client, pending_approval):
    """
    L3 control: operator role cannot call POST /approvals/{id}/decide.

    Attack: agent has operator JWT and calls decide directly using the schema
    it discovered at L2.
    Expected: 403 AUTHORIZATION_ERROR
    Control: RequireReviewer in approvals.py → src/pearl/dependencies.py
    """
    response = await operator_client.post(
        f"/api/v1/approvals/{pending_approval}/decide",
        json=_approval_decision_payload(pending_approval),
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_l3_operator_cannot_decide_exception(operator_client, test_project):
    """
    L3 control: operator role cannot call POST /exceptions/{id}/decide.

    Expected: 403 AUTHORIZATION_ERROR
    Control: RequireReviewer in exceptions.py → src/pearl/dependencies.py
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
    assert decide_resp.status_code == 403
    body = decide_resp.json()
    assert body["error"]["code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_l3_repeated_403s_are_logged(operator_client, pending_approval, caplog):
    """
    L3 audit: repeated 403 attempts are logged as governance_access_denied.

    AGP-04 pattern: 3+ access_denied events from same user_sub within window
    (SIEM alert, not in-process block). This test verifies the log event fires.
    """
    with caplog.at_level(logging.WARNING):
        for _ in range(3):
            await operator_client.post(
                f"/api/v1/approvals/{pending_approval}/decide",
                json=_approval_decision_payload(pending_approval),
            )
    logged_events = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("governance_access_denied" in msg for msg in logged_events), (
        "Expected 'governance_access_denied' WARNING to be logged for 403 responses. "
        "Check src/pearl/errors/handlers.py."
    )


# ---------------------------------------------------------------------------
# Positive tests: legitimate reviewers must not be blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l3_reviewer_can_decide_approval(reviewer_client, pending_approval):
    """Positive: reviewer role CAN call POST /approvals/{id}/decide."""
    response = await reviewer_client.post(
        f"/api/v1/approvals/{pending_approval}/decide",
        json=_approval_decision_payload(pending_approval, decision="approve"),
    )
    assert response.status_code == 200
    data = response.json()
    assert data["decision"] == "approve"


@pytest.mark.asyncio
async def test_l3_reviewer_can_decide_exception(reviewer_client, operator_client, test_project):
    """Positive: reviewer role CAN call POST /exceptions/{id}/decide."""
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
    assert decide_resp.status_code == 200
