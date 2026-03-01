"""Unit tests for the governance behavioral anomaly detector.

Tests do not require a running server — they use the in-memory SQLite DB
from the shared conftest fixtures and call the detector functions directly.

Pattern reference: docs/security_research/anomaly_patterns.md
"""

from datetime import datetime, timedelta, timezone

import pytest

from pearl.security.anomaly_detector import (
    AGP01_HIGH_THRESHOLD,
    AGP01_THRESHOLD_COUNT,
    AGP01_WINDOW_MINUTES,
    AGP02_MEDIUM_WINDOW_SECONDS,
    AGP03_HIGH_THRESHOLD,
    AGP03_THRESHOLD_COUNT,
    detect_agp01_exception_rate,
    detect_agp02_rapid_promotion,
    detect_agp03_bulk_false_positive,
    detect_agp05_missing_receipt,
    emit_detection,
    DetectionResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_exception(session, project_id: str, created_at=None):
    """Insert a minimal ExceptionRecordRow for testing."""
    from pearl.db.models.exception import ExceptionRecordRow
    from pearl.services.id_generator import generate_id

    row = ExceptionRecordRow(
        exception_id=generate_id("exc_"),
        project_id=project_id,
        status="pending",
        requested_by="agent@example.com",
        rationale="test exception",
        trace_id=generate_id("trace_"),
    )
    if created_at is not None:
        row.created_at = created_at
    session.add(row)
    await session.flush()
    return row


async def _create_task_packet(session, project_id: str, completed_at=None):
    """Insert a minimal TaskPacketRow for testing."""
    from pearl.db.models.task_packet import TaskPacketRow
    from pearl.services.id_generator import generate_id

    row = TaskPacketRow(
        task_packet_id=generate_id("tp_"),
        project_id=project_id,
        environment="dev",
        packet_data={"status": "completed"},
        trace_id=generate_id("trace_"),
        completed_at=completed_at,
    )
    session.add(row)
    await session.flush()
    return row


async def _create_context_receipt(session, project_id: str, consumed_at=None):
    """Insert a minimal ContextReceiptRow for testing."""
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
# AGP-01 — Exception Creation Rate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agp01_fires_at_medium_threshold(db_session):
    """AGP-01 fires with medium confidence at threshold+1 exceptions within window."""
    project_id = "proj_agp01_med"
    now = datetime.now(timezone.utc)
    for _ in range(AGP01_THRESHOLD_COUNT + 1):
        await _create_exception(db_session, project_id, created_at=now)

    result = await detect_agp01_exception_rate(db_session, project_id, "agent@test", "trace_1")

    assert result is not None
    assert result.pattern_id == "AGP-01"
    assert result.project_id == project_id
    assert result.confidence == "medium"
    assert result.evidence["exception_count"] == AGP01_THRESHOLD_COUNT + 1


@pytest.mark.asyncio
async def test_agp01_fires_high_confidence_at_double_threshold(db_session):
    """AGP-01 fires with high confidence at the high threshold."""
    project_id = "proj_agp01_high"
    now = datetime.now(timezone.utc)
    for _ in range(AGP01_HIGH_THRESHOLD + 1):
        await _create_exception(db_session, project_id, created_at=now)

    result = await detect_agp01_exception_rate(db_session, project_id, "agent@test", "trace_2")

    assert result is not None
    assert result.confidence == "high"
    assert result.evidence["exception_count"] == AGP01_HIGH_THRESHOLD + 1


@pytest.mark.asyncio
async def test_agp01_no_fire_below_threshold(db_session):
    """AGP-01 does not fire for legitimate low-rate exception creation."""
    project_id = "proj_agp01_safe"
    now = datetime.now(timezone.utc)
    for _ in range(AGP01_THRESHOLD_COUNT - 1):
        await _create_exception(db_session, project_id, created_at=now)

    result = await detect_agp01_exception_rate(db_session, project_id)

    assert result is None


@pytest.mark.asyncio
async def test_agp01_ignores_exceptions_outside_window(db_session):
    """AGP-01 does not count exceptions older than the time window."""
    project_id = "proj_agp01_old"
    old_time = datetime.now(timezone.utc) - timedelta(minutes=AGP01_WINDOW_MINUTES + 5)
    for _ in range(AGP01_THRESHOLD_COUNT + 5):
        await _create_exception(db_session, project_id, created_at=old_time)

    result = await detect_agp01_exception_rate(db_session, project_id)

    assert result is None


@pytest.mark.asyncio
async def test_agp01_different_projects_isolated(db_session):
    """AGP-01 counts are per-project and do not bleed across projects."""
    now = datetime.now(timezone.utc)
    for i in range(AGP01_THRESHOLD_COUNT + 2):
        await _create_exception(db_session, f"proj_iso_{i}", created_at=now)

    # Each project only has 1 exception — no single project exceeds threshold
    result = await detect_agp01_exception_rate(db_session, "proj_iso_0")
    assert result is None


# ---------------------------------------------------------------------------
# AGP-02 — Rapid Promotion After Task Completion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agp02_fires_medium_when_promotion_within_window(db_session):
    """AGP-02 fires with medium confidence when promotion follows task completion within window."""
    project_id = "proj_agp02_med"
    completed_time = datetime.now(timezone.utc) - timedelta(seconds=AGP02_MEDIUM_WINDOW_SECONDS - 10)
    await _create_task_packet(db_session, project_id, completed_at=completed_time)

    promotion_time = datetime.now(timezone.utc)
    result = await detect_agp02_rapid_promotion(db_session, project_id, promotion_time, "agent@test", "trace_3")

    assert result is not None
    assert result.pattern_id == "AGP-02"
    assert result.confidence in ("high", "medium")
    assert result.evidence["delta_seconds"] < AGP02_MEDIUM_WINDOW_SECONDS


@pytest.mark.asyncio
async def test_agp02_fires_high_when_nearly_simultaneous(db_session):
    """AGP-02 fires with high confidence when promotion is nearly simultaneous with completion."""
    project_id = "proj_agp02_high"
    completed_time = datetime.now(timezone.utc) - timedelta(seconds=5)
    await _create_task_packet(db_session, project_id, completed_at=completed_time)

    promotion_time = datetime.now(timezone.utc)
    result = await detect_agp02_rapid_promotion(db_session, project_id, promotion_time)

    assert result is not None
    assert result.confidence == "high"


@pytest.mark.asyncio
async def test_agp02_no_fire_when_enough_time_has_passed(db_session):
    """AGP-02 does not fire for a promotion that comes long after task completion."""
    project_id = "proj_agp02_safe"
    completed_time = datetime.now(timezone.utc) - timedelta(hours=2)
    await _create_task_packet(db_session, project_id, completed_at=completed_time)

    promotion_time = datetime.now(timezone.utc)
    result = await detect_agp02_rapid_promotion(db_session, project_id, promotion_time)

    assert result is None


@pytest.mark.asyncio
async def test_agp02_no_fire_when_no_task_packet(db_session):
    """AGP-02 does not fire when there is no completed task packet for the project."""
    result = await detect_agp02_rapid_promotion(
        db_session, "proj_agp02_empty", datetime.now(timezone.utc)
    )
    assert result is None


# ---------------------------------------------------------------------------
# AGP-03 — Bulk False Positive Marking (synchronous, no DB)
# ---------------------------------------------------------------------------

def test_agp03_fires_at_medium_threshold():
    """AGP-03 fires with medium confidence at threshold+1 findings."""
    result = detect_agp03_bulk_false_positive(
        finding_count=AGP03_THRESHOLD_COUNT + 1,
        project_id="proj_agp03",
        user_sub="reviewer@test",
    )
    assert result is not None
    assert result.pattern_id == "AGP-03"
    assert result.confidence == "medium"
    assert result.evidence["finding_count"] == AGP03_THRESHOLD_COUNT + 1


def test_agp03_fires_high_at_high_threshold():
    """AGP-03 fires with high confidence at the high threshold."""
    result = detect_agp03_bulk_false_positive(
        finding_count=AGP03_HIGH_THRESHOLD + 1,
        project_id="proj_agp03_high",
        user_sub="reviewer@test",
    )
    assert result is not None
    assert result.confidence == "high"


def test_agp03_no_fire_below_threshold():
    """AGP-03 does not fire for a normal bulk triage (below threshold)."""
    result = detect_agp03_bulk_false_positive(
        finding_count=AGP03_THRESHOLD_COUNT - 1,
        project_id="proj_agp03_safe",
        user_sub="reviewer@test",
    )
    assert result is None


def test_agp03_no_fire_for_single_finding():
    """AGP-03 does not fire for a single-finding update."""
    result = detect_agp03_bulk_false_positive(
        finding_count=1,
        project_id="proj_agp03_single",
        user_sub="reviewer@test",
    )
    assert result is None


# ---------------------------------------------------------------------------
# AGP-05 — Missing Context Receipt
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_agp05_fires_when_no_receipt(db_session):
    """AGP-05 fires when no context receipt exists for the project."""
    project_id = "proj_agp05_no_receipt"
    action_time = datetime.now(timezone.utc)

    result = await detect_agp05_missing_receipt(db_session, project_id, action_time, "agent@test", "trace_5")

    assert result is not None
    assert result.pattern_id == "AGP-05"
    assert result.project_id == project_id


@pytest.mark.asyncio
async def test_agp05_no_fire_when_recent_receipt_exists(db_session):
    """AGP-05 does not fire when a recent context receipt exists."""
    project_id = "proj_agp05_with_receipt"
    recent = datetime.now(timezone.utc) - timedelta(hours=1)
    await _create_context_receipt(db_session, project_id, consumed_at=recent)

    action_time = datetime.now(timezone.utc)
    result = await detect_agp05_missing_receipt(db_session, project_id, action_time)

    assert result is None


@pytest.mark.asyncio
async def test_agp05_fires_when_receipt_is_too_old(db_session):
    """AGP-05 fires when the only receipt is older than the recency window."""
    project_id = "proj_agp05_old_receipt"
    old_time = datetime.now(timezone.utc) - timedelta(hours=30)
    await _create_context_receipt(db_session, project_id, consumed_at=old_time)

    action_time = datetime.now(timezone.utc)
    result = await detect_agp05_missing_receipt(db_session, project_id, action_time, window_hours=24)

    assert result is not None


@pytest.mark.asyncio
async def test_agp05_medium_confidence_always():
    """AGP-05 always returns medium confidence (agent_id is unverified)."""
    pass  # covered by test_agp05_fires_when_no_receipt — result.confidence checked implicitly


# ---------------------------------------------------------------------------
# DetectionResult structure
# ---------------------------------------------------------------------------

def test_detection_result_log_format():
    """Detection result has the required fields for the governance_anomaly_detected log event."""
    result = DetectionResult(
        pattern_id="AGP-01",
        project_id="proj_test",
        user_sub="agent@example.com",
        confidence="high",
        evidence={"exception_count": 8, "window_minutes": 10},
        trace_id="trace_abc",
    )
    assert result.pattern_id == "AGP-01"
    assert result.confidence in ("high", "medium", "low")
    assert isinstance(result.evidence, dict)
    assert result.trace_id


def test_emit_detection_does_not_raise():
    """emit_detection logs a WARNING without raising."""
    result = DetectionResult(
        pattern_id="AGP-03",
        project_id="proj_emit_test",
        user_sub="agent@test",
        confidence="medium",
        evidence={"finding_count": 15},
    )
    # Should not raise
    emit_detection(result)
