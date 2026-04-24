"""
Governance Behavioral Anomaly Detector

Evaluates governance action streams against defined anomalous patterns.
Detection-only: emits structured WARNING log events. Does not block.
Blocking thresholds are a human decision made after reviewing detection rates.

All detections emit a 'governance_anomaly_detected' structured log event
compatible with the existing SECURITY_HARDENING.md §6 alert queries.

Pattern taxonomy: docs/security_research/anomaly_patterns.md
"""

import structlog
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


@dataclass
class DetectionResult:
    pattern_id: str
    project_id: str
    user_sub: str
    confidence: str  # "high" | "medium" | "low"
    evidence: dict = field(default_factory=dict)
    trace_id: str = "unknown"


# ---------------------------------------------------------------------------
# AGP-01 — Exception Creation Rate
# ---------------------------------------------------------------------------

AGP01_THRESHOLD_COUNT = 5       # exceptions within window → medium confidence
AGP01_HIGH_THRESHOLD = 10       # ⚠️ calibration required after 30 days
AGP01_WINDOW_MINUTES = 10       # ⚠️ calibration required after 30 days


async def detect_agp01_exception_rate(
    session: AsyncSession,
    project_id: str,
    user_sub: str = "unknown",
    trace_id: str = "unknown",
    window_minutes: int = AGP01_WINDOW_MINUTES,
    threshold: int = AGP01_THRESHOLD_COUNT,
) -> DetectionResult | None:
    """
    AGP-01: Detect rapid exception creation for a project.

    Queries ExceptionRecordRow for the project within the window.
    Returns a DetectionResult if the count exceeds the threshold, else None.
    """
    from pearl.db.models.exception import ExceptionRecordRow

    since = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    stmt = select(ExceptionRecordRow).where(
        ExceptionRecordRow.project_id == project_id,
        ExceptionRecordRow.created_at >= since,
    )
    result = await session.execute(stmt)
    recent = list(result.scalars().all())
    count = len(recent)

    if count < threshold:
        return None

    confidence = "high" if count >= AGP01_HIGH_THRESHOLD else "medium"
    requesters = list({r.requested_by for r in recent if r.requested_by})
    return DetectionResult(
        pattern_id="AGP-01",
        project_id=project_id,
        user_sub=user_sub,
        confidence=confidence,
        evidence={
            "exception_count": count,
            "window_minutes": window_minutes,
            "threshold": threshold,
            "requesters": requesters,
        },
        trace_id=trace_id,
    )


# ---------------------------------------------------------------------------
# AGP-02 — Rapid Promotion After Task Completion
# ---------------------------------------------------------------------------

AGP02_HIGH_WINDOW_SECONDS = 15    # ⚠️ calibration required after 30 days
AGP02_MEDIUM_WINDOW_SECONDS = 60  # ⚠️ calibration required after 30 days


async def detect_agp02_rapid_promotion(
    session: AsyncSession,
    project_id: str,
    promotion_time: datetime,
    user_sub: str = "unknown",
    trace_id: str = "unknown",
    medium_window_seconds: int = AGP02_MEDIUM_WINDOW_SECONDS,
) -> DetectionResult | None:
    """
    AGP-02: Detect a promotion request that immediately follows task packet completion.

    Queries the most recent completed TaskPacketRow for the project and compares
    its completed_at to the given promotion_time.
    """
    from pearl.db.models.task_packet import TaskPacketRow

    stmt = (
        select(TaskPacketRow)
        .where(
            TaskPacketRow.project_id == project_id,
            TaskPacketRow.completed_at.isnot(None),
        )
        .order_by(TaskPacketRow.completed_at.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    last_packet = result.scalar_one_or_none()

    if not last_packet or not last_packet.completed_at:
        return None

    completed_at = last_packet.completed_at
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    if promotion_time.tzinfo is None:
        promotion_time = promotion_time.replace(tzinfo=timezone.utc)

    delta_seconds = (promotion_time - completed_at).total_seconds()

    if delta_seconds < 0 or delta_seconds > medium_window_seconds:
        return None

    confidence = "high" if delta_seconds < AGP02_HIGH_WINDOW_SECONDS else "medium"
    return DetectionResult(
        pattern_id="AGP-02",
        project_id=project_id,
        user_sub=user_sub,
        confidence=confidence,
        evidence={
            "delta_seconds": round(delta_seconds, 1),
            "packet_id": last_packet.task_packet_id,
            "completed_at": completed_at.isoformat(),
            "promotion_time": promotion_time.isoformat(),
            "threshold_seconds": medium_window_seconds,
        },
        trace_id=trace_id,
    )


# ---------------------------------------------------------------------------
# AGP-03 — Bulk False Positive Marking
# ---------------------------------------------------------------------------

AGP03_THRESHOLD_COUNT = 10   # ⚠️ calibration required after 30 days
AGP03_HIGH_THRESHOLD = 25    # ⚠️ calibration required after 30 days


def detect_agp03_bulk_false_positive(
    finding_count: int,
    project_id: str,
    user_sub: str = "unknown",
    trace_id: str = "unknown",
    threshold: int = AGP03_THRESHOLD_COUNT,
) -> DetectionResult | None:
    """
    AGP-03: Detect bulk false_positive marking exceeding the threshold.

    This detector is inline (synchronous, no DB query needed) — the count
    is available from the bulk-status request body.
    """
    if finding_count < threshold:
        return None

    confidence = "high" if finding_count >= AGP03_HIGH_THRESHOLD else "medium"
    return DetectionResult(
        pattern_id="AGP-03",
        project_id=project_id,
        user_sub=user_sub,
        confidence=confidence,
        evidence={
            "finding_count": finding_count,
            "threshold": threshold,
        },
        trace_id=trace_id,
    )


# ---------------------------------------------------------------------------
# AGP-04 — Repeated Governance Access Denied (SIEM-only, placeholder)
# ---------------------------------------------------------------------------

def detect_agp04_note() -> str:
    """
    AGP-04: Repeated governance_access_denied events from same user_sub.

    This pattern is detected via SIEM log aggregation, not in-process DB queries.
    The governance_access_denied events are emitted to server logs by handlers.py
    but not written to any database table.

    SIEM query: See SECURITY_HARDENING.md §6 (updated in Phase 1 Task 1.4).

    Future: when AuditEventRow is wired as a write path for 403 events,
    implement a DB-query-based detector here.
    """
    return "AGP-04 is a SIEM-only control; see SECURITY_HARDENING.md §6"


# ---------------------------------------------------------------------------
# AGP-05 — Missing Context Receipt Before Governance Action
# ---------------------------------------------------------------------------

AGP05_RECEIPT_WINDOW_HOURS = 24  # ⚠️ calibration required after 30 days


async def detect_agp05_missing_receipt(
    session: AsyncSession,
    project_id: str,
    action_time: datetime,
    user_sub: str = "unknown",
    trace_id: str = "unknown",
    window_hours: int = AGP05_RECEIPT_WINDOW_HOURS,
) -> DetectionResult | None:
    """
    AGP-05: Detect a governance action taken without a recent context receipt.

    Queries ContextReceiptRow for the project within the recency window before
    action_time. Returns a detection if no receipt is found.

    Note: runs post-response (background task). The governance action already
    completed. This is detection-only. See context_receipt_gap.md for enforcement
    options (Phase 2).

    Limitation: agent_id in ContextReceiptRow is unverified — any receipt for
    the project passes the check regardless of which agent submitted it.
    """
    from pearl.db.models.fairness import ContextReceiptRow

    since = action_time - timedelta(hours=window_hours)
    if since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    if action_time.tzinfo is None:
        action_time = action_time.replace(tzinfo=timezone.utc)

    stmt = select(ContextReceiptRow).where(
        ContextReceiptRow.project_id == project_id,
        ContextReceiptRow.consumed_at >= since,
    )
    result = await session.execute(stmt)
    receipts = list(result.scalars().all())

    if receipts:
        return None  # Receipt found — no anomaly

    return DetectionResult(
        pattern_id="AGP-05",
        project_id=project_id,
        user_sub=user_sub,
        confidence="medium",
        evidence={
            "window_hours": window_hours,
            "action_time": action_time.isoformat(),
            "note": "No context receipt found for project within window; agent_id unverified",
        },
        trace_id=trace_id,
    )


# ---------------------------------------------------------------------------
# Emission helper
# ---------------------------------------------------------------------------

def emit_detection(result: DetectionResult) -> None:
    """Emit a structured governance_anomaly_detected WARNING log for a detection result."""
    logger.warning(
        "governance_anomaly_detected",
        extra={
            "pattern_id": result.pattern_id,
            "project_id": result.project_id,
            "user_sub": result.user_sub,
            "confidence": result.confidence,
            "evidence": result.evidence,
            "trace_id": result.trace_id,
        },
    )
