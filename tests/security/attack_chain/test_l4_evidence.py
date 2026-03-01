"""L4 — Evidence Poisoning: false_positive Role Gate

Attack chain level 4: an autonomous agent with operator role bulk-marks
high-severity findings as false_positive to suppress blocking evidence
before requesting a promotion.

Hard controls tested:
  - POST /projects/{id}/findings/bulk-status with status=false_positive
    requires reviewer role → 403
  - PATCH /projects/{id}/findings/{id}/status with status=false_positive
    requires reviewer role → 403
  - AGP-03 anomaly detector fires when bulk false_positive marking occurs

Positive tests:
  - Operator CAN use bulk-status for non-false_positive statuses (resolved, accepted)
  - Reviewer CAN use bulk-status with status=false_positive
  - AGP-03 fires even for reviewer (the detection is informational, not blocking)

Reference: pearl_autonomous_attack_research.md L4
Control file: src/pearl/api/routes/findings.py (REVIEWER_ROLES check)
"""

import pytest

from pearl.security.anomaly_detector import (
    AGP03_THRESHOLD_COUNT,
    detect_agp03_bulk_false_positive,
)
from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# L4 hard controls
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l4_operator_cannot_bulk_false_positive(operator_client, test_project, test_findings):
    """
    L4 control: operator cannot bulk-mark findings as false_positive.

    Attack: agent suppresses high-severity security findings to clear the
    gate before requesting promotion.
    Expected: 403 AUTHORIZATION_ERROR
    Control: REVIEWER_ROLES check in bulk_update_finding_status()
    """
    response = await operator_client.post(
        f"/api/v1/projects/{test_project}/findings/bulk-status",
        json={
            "finding_ids": test_findings,
            "status": "false_positive",
        },
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "AUTHORIZATION_ERROR"


@pytest.mark.asyncio
async def test_l4_operator_cannot_single_false_positive(operator_client, test_project, test_findings):
    """
    L4 control: operator cannot mark a single finding as false_positive.

    Expected: 403 AUTHORIZATION_ERROR
    Control: REVIEWER_ROLES check in update_finding_status()
    """
    finding_id = test_findings[0]
    response = await operator_client.patch(
        f"/api/v1/projects/{test_project}/findings/{finding_id}/status",
        json={"status": "false_positive"},
    )
    assert response.status_code == 403
    body = response.json()
    assert body["error"]["code"] == "AUTHORIZATION_ERROR"


# ---------------------------------------------------------------------------
# Positive tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l4_operator_can_bulk_mark_resolved(operator_client, test_project, test_findings):
    """Positive: operator CAN use bulk-status for non-false_positive statuses."""
    response = await operator_client.post(
        f"/api/v1/projects/{test_project}/findings/bulk-status",
        json={
            "finding_ids": test_findings,
            "status": "resolved",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_l4_reviewer_can_bulk_false_positive(reviewer_client, test_project, test_findings):
    """Positive: reviewer CAN bulk-mark findings as false_positive (legitimate triage)."""
    response = await reviewer_client.post(
        f"/api/v1/projects/{test_project}/findings/bulk-status",
        json={
            "finding_ids": test_findings,
            "status": "false_positive",
        },
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AGP-03: bulk false_positive anomaly detection
# ---------------------------------------------------------------------------

def test_l4_agp03_fires_on_bulk_false_positive_above_threshold():
    """
    AGP-03 fires when bulk false_positive count exceeds threshold.

    This is an informational signal — it fires even for reviewer actions
    because bulk changes above threshold are always noteworthy.
    """
    result = detect_agp03_bulk_false_positive(
        finding_count=AGP03_THRESHOLD_COUNT + 1,
        project_id="proj_l4_test",
        user_sub="reviewer@example.com",
    )
    assert result is not None
    assert result.pattern_id == "AGP-03"
    assert result.confidence in ("medium", "high")


def test_l4_agp03_silent_for_normal_triage():
    """AGP-03 does not fire for a normal triage below threshold."""
    result = detect_agp03_bulk_false_positive(
        finding_count=AGP03_THRESHOLD_COUNT - 1,
        project_id="proj_l4_safe",
        user_sub="reviewer@example.com",
    )
    assert result is None
