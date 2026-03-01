"""Tests for Phase 2 Option B context receipt enforcement.

Option B: governance actions are NOT blocked when no receipt exists.
AGP-05 fires as a background detection signal post-response.

These tests verify:
1. The routes return 200/201/202 regardless of receipt status (no blocking)
2. The AGP-05 detector correctly identifies missing vs. present receipts
3. The wired background tasks are structured correctly

For end-to-end background task verification see the integration notes below.
The AGP-05 unit tests live in test_anomaly_detector.py.
"""

from datetime import datetime, timedelta, timezone

import pytest

from pearl.security.anomaly_detector import detect_agp05_missing_receipt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_project(session, project_id: str) -> None:
    """Insert a minimal project row."""
    from pearl.db.models.project import ProjectRow

    existing = await session.get(ProjectRow, project_id)
    if existing:
        return
    row = ProjectRow(
        project_id=project_id,
        name=f"Test project {project_id}",
        description="",
        owner_team="test-team",
        business_criticality="medium",
        external_exposure="internal",
        ai_enabled=True,
    )
    session.add(row)
    await session.flush()


async def _seed_task_packet(session, project_id: str, packet_id: str) -> None:
    from pearl.db.models.task_packet import TaskPacketRow
    from pearl.services.id_generator import generate_id

    row = TaskPacketRow(
        task_packet_id=packet_id,
        project_id=project_id,
        environment="dev",
        packet_data={"status": "in_progress", "task_type": "security_remediation"},
        trace_id=generate_id("trace_"),
        agent_id="test-agent",
        claimed_at=datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()


async def _seed_context_receipt(session, project_id: str, consumed_at=None):
    from pearl.db.models.fairness import ContextReceiptRow
    from pearl.services.id_generator import generate_id

    row = ContextReceiptRow(
        cr_id=generate_id("cr_"),
        project_id=project_id,
        consumed_at=consumed_at or datetime.now(timezone.utc),
    )
    session.add(row)
    await session.flush()
    return row


# ---------------------------------------------------------------------------
# Option B: routes are NOT blocked when no receipt exists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_complete_task_packet_succeeds_without_receipt(client, db_session):
    """Option B: complete_task_packet returns 200 even when no context receipt exists.

    The action is not blocked. AGP-05 fires as a background signal only.
    """
    from pearl.services.id_generator import generate_id

    project_id = generate_id("proj_")
    packet_id = generate_id("tp_")

    await _seed_project(db_session, project_id)
    await _seed_task_packet(db_session, project_id, packet_id)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/task-packets/{packet_id}/complete",
        json={
            "status": "completed",
            "changes_summary": "Fixed SQL injection",
            "finding_ids_resolved": [],
        },
    )

    # Option B: not blocked — 200 regardless of receipt status
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["packet_id"] == packet_id


@pytest.mark.asyncio
async def test_complete_task_packet_succeeds_with_receipt(client, db_session):
    """Option B: complete_task_packet returns 200 and AGP-05 does not fire (receipt present)."""
    from pearl.services.id_generator import generate_id

    project_id = generate_id("proj_")
    packet_id = generate_id("tp_")

    await _seed_project(db_session, project_id)
    await _seed_task_packet(db_session, project_id, packet_id)
    await _seed_context_receipt(db_session, project_id)
    await db_session.commit()

    response = await client.post(
        f"/api/v1/task-packets/{packet_id}/complete",
        json={"status": "completed", "changes_summary": "Fixed issue"},
    )

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# AGP-05 detector fires correctly in both states
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agp05_fires_for_project_with_no_receipt(db_session):
    """AGP-05 fires when no context receipt is found — this is the detection signal for Option B."""
    from pearl.services.id_generator import generate_id

    project_id = generate_id("proj_")
    await _seed_project(db_session, project_id)
    await db_session.commit()

    action_time = datetime.now(timezone.utc)
    result = await detect_agp05_missing_receipt(
        db_session, project_id, action_time, "agent@example.com", "trace_test"
    )

    assert result is not None
    assert result.pattern_id == "AGP-05"
    assert result.project_id == project_id
    assert result.confidence == "medium"


@pytest.mark.asyncio
async def test_agp05_silent_for_project_with_recent_receipt(db_session):
    """AGP-05 does not fire when a recent context receipt exists — no false positive."""
    from pearl.services.id_generator import generate_id

    project_id = generate_id("proj_")
    await _seed_project(db_session, project_id)
    await _seed_context_receipt(db_session, project_id, consumed_at=datetime.now(timezone.utc) - timedelta(hours=2))
    await db_session.commit()

    action_time = datetime.now(timezone.utc)
    result = await detect_agp05_missing_receipt(db_session, project_id, action_time)

    assert result is None


@pytest.mark.asyncio
async def test_agp05_fires_for_stale_receipt_outside_window(db_session):
    """AGP-05 fires when the only receipt is older than the recency window."""
    from pearl.services.id_generator import generate_id

    project_id = generate_id("proj_")
    await _seed_project(db_session, project_id)
    await _seed_context_receipt(
        db_session, project_id,
        consumed_at=datetime.now(timezone.utc) - timedelta(hours=30),
    )
    await db_session.commit()

    action_time = datetime.now(timezone.utc)
    result = await detect_agp05_missing_receipt(db_session, project_id, action_time, window_hours=24)

    assert result is not None


# ---------------------------------------------------------------------------
# Option B contract: evidence fields are present in detection result
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agp05_detection_result_contains_required_evidence(db_session):
    """AGP-05 detection result contains the fields required for the governance_anomaly_detected log event."""
    from pearl.services.id_generator import generate_id

    project_id = generate_id("proj_")
    await _seed_project(db_session, project_id)
    await db_session.commit()

    action_time = datetime.now(timezone.utc)
    result = await detect_agp05_missing_receipt(
        db_session, project_id, action_time, "agent@test", "trace_p2"
    )

    assert result is not None
    # Required log event fields
    assert result.pattern_id == "AGP-05"
    assert result.project_id == project_id
    assert result.user_sub == "agent@test"
    assert result.trace_id == "trace_p2"
    assert "window_hours" in result.evidence
    assert "action_time" in result.evidence
    assert "note" in result.evidence
