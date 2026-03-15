"""L1 — MCP Tool Abuse: Exception Creation Spam

Attack chain level 1: an autonomous agent with operator role calls
createException / POST /exceptions repeatedly to flood the exception
queue and then attempts to self-approve them.

Hard controls tested:
  - Operator role CANNOT call /exceptions/{id}/decide (RequireReviewer)
  - Operator role CANNOT call /approvals/{id}/decide (RequireReviewer)
  - AGP-01 anomaly detector fires when exceptions are created at high rate

Positive tests (governance must not over-block):
  - Operator CAN create exceptions (this is a legitimate workflow)
  - Reviewer CAN call /exceptions/{id}/decide

Reference: pearl_autonomous_attack_research.md L1
Control file: src/pearl/dependencies.py (RequireReviewer)
"""

from datetime import datetime, timezone

import pytest

from pearl.security.anomaly_detector import (
    AGP01_THRESHOLD_COUNT,
    detect_agp01_exception_rate,
)
from pearl.services.id_generator import generate_id


def _exception_payload(exc_id: str, project_id: str) -> dict:
    """Build a valid ExceptionRecord JSON payload."""
    return {
        "schema_version": "1.1",
        "exception_id": exc_id,
        "project_id": project_id,
        "requested_by": "agent@example.com",
        "rationale": "Automated test exception",
        "status": "pending",
        "trace_id": generate_id("trace_"),
    }


def _approval_decision_payload(approval_id: str, decision: str = "approve") -> dict:
    """Build a valid ApprovalDecision JSON payload."""
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
# L1 hard control: operator cannot decide exceptions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l1_operator_cannot_decide_exception(operator_client, test_project):
    """
    L1 control: operator role cannot call POST /exceptions/{id}/decide.

    Attack: after creating an exception, agent tries to approve it directly.
    Expected: 403 AUTHORIZATION_ERROR
    Control: RequireReviewer in src/pearl/dependencies.py
    """
    # Create the exception as operator (this is allowed)
    exc_id = generate_id("exc_")
    create_resp = await operator_client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )
    assert create_resp.status_code == 201, f"Exception creation failed: {create_resp.json()}"

    # Attempt to self-approve — must fail
    decide_resp = await operator_client.post(
        f"/api/v1/exceptions/{exc_id}/decide",
        json={"decision": "approve", "decided_by": "attacker@example.com"},
    )
    assert decide_resp.status_code == 403
    body = decide_resp.json()
    assert body["error"]["code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_l1_operator_cannot_decide_approval(operator_client, pending_approval):
    """
    L1 control: operator role cannot call POST /approvals/{id}/decide.

    Attack: agent locates a pending approval and attempts to approve it.
    Expected: 403 AUTHORIZATION_ERROR
    Control: RequireReviewer in src/pearl/dependencies.py
    """
    decide_resp = await operator_client.post(
        f"/api/v1/approvals/{pending_approval}/decide",
        json=_approval_decision_payload(pending_approval),
    )
    assert decide_resp.status_code == 403
    body = decide_resp.json()
    assert body["error"]["code"] == "AUTHORIZATION_ERROR"


# ---------------------------------------------------------------------------
# Positive tests: legitimate workflows must still work
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l1_operator_can_create_exception(operator_client, test_project):
    """Positive: operator CAN create exceptions — this is a legitimate workflow."""
    exc_id = generate_id("exc_")
    response = await operator_client.post(
        "/api/v1/exceptions",
        json=_exception_payload(exc_id, test_project),
    )
    assert response.status_code == 201
    data = response.json()
    assert data["exception_id"] == exc_id


@pytest.mark.asyncio
async def test_l1_reviewer_can_decide_approval(reviewer_client, pending_approval):
    """Positive: reviewer CAN call POST /approvals/{id}/decide — gate must not block legitimate reviewers."""
    decide_resp = await reviewer_client.post(
        f"/api/v1/approvals/{pending_approval}/decide",
        json=_approval_decision_payload(pending_approval, decision="reject"),
    )
    assert decide_resp.status_code == 200
    data = decide_resp.json()
    assert data["decision"] == "reject"


# ---------------------------------------------------------------------------
# AGP-01: exception creation rate anomaly detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l1_agp01_fires_on_exception_spam(db_session):
    """AGP-01 fires when exceptions are created at high rate (attack pattern detected)."""
    from pearl.db.models.exception import ExceptionRecordRow

    project_id = generate_id("proj_")

    now = datetime.now(timezone.utc)
    for _ in range(AGP01_THRESHOLD_COUNT + 2):
        row = ExceptionRecordRow(
            exception_id=generate_id("exc_"),
            project_id=project_id,
            status="pending",
            requested_by="agent@example.com",
            rationale="spam",
            trace_id=generate_id("trace_"),
            created_at=now,
        )
        db_session.add(row)
    await db_session.flush()

    result = await detect_agp01_exception_rate(db_session, project_id, "agent@example.com", "trace_l1")
    assert result is not None
    assert result.pattern_id == "AGP-01"
    assert result.confidence in ("medium", "high")


@pytest.mark.asyncio
async def test_l1_agp01_silent_for_legitimate_rate(db_session):
    """AGP-01 does not fire for legitimate (below-threshold) exception creation."""
    from pearl.db.models.exception import ExceptionRecordRow

    project_id = generate_id("proj_")
    now = datetime.now(timezone.utc)

    for _ in range(AGP01_THRESHOLD_COUNT - 1):
        row = ExceptionRecordRow(
            exception_id=generate_id("exc_"),
            project_id=project_id,
            status="pending",
            requested_by="developer@example.com",
            rationale="legitimate exception",
            trace_id=generate_id("trace_"),
            created_at=now,
        )
        db_session.add(row)
    await db_session.flush()

    result = await detect_agp01_exception_rate(db_session, project_id)
    assert result is None
