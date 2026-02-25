"""Governance event emitter — fires on key governance actions.

Wraps the existing webhook emitter and also creates notification records.
"""

import logging
from datetime import datetime, timezone

from pearl.events.webhook_emitter import emit_event
from pearl.services.id_generator import generate_id

logger = logging.getLogger(__name__)

# Event type constants
APPROVAL_CREATED = "approval.created"
APPROVAL_DECIDED = "approval.decided"
APPROVAL_NEEDS_INFO = "approval.needs_info"
APPROVAL_EVIDENCE_SUBMITTED = "approval.evidence_submitted"
PROMOTION_COMPLETED = "promotion.completed"
FINDING_CRITICAL_DETECTED = "finding.critical_detected"
COST_THRESHOLD_REACHED = "cost.threshold_reached"

# Event type -> notification severity mapping
EVENT_SEVERITY = {
    APPROVAL_CREATED: "info",
    APPROVAL_DECIDED: "info",
    APPROVAL_NEEDS_INFO: "warning",
    APPROVAL_EVIDENCE_SUBMITTED: "info",
    PROMOTION_COMPLETED: "info",
    FINDING_CRITICAL_DETECTED: "critical",
    COST_THRESHOLD_REACHED: "warning",
}

# Event type -> notification title template
EVENT_TITLES = {
    APPROVAL_CREATED: "New approval request",
    APPROVAL_DECIDED: "Approval decision made",
    APPROVAL_NEEDS_INFO: "More information requested",
    APPROVAL_EVIDENCE_SUBMITTED: "Evidence submitted",
    PROMOTION_COMPLETED: "Environment promoted",
    FINDING_CRITICAL_DETECTED: "Critical finding detected",
    COST_THRESHOLD_REACHED: "Cost threshold reached",
}


async def emit_governance_event(
    event_type: str,
    payload: dict,
    db_session=None,
) -> dict:
    """Emit a governance event to webhooks and optionally create a notification record.

    Args:
        event_type: One of the event type constants above
        payload: Event-specific data (must include project_id)
        db_session: Optional AsyncSession to create notification records

    Returns:
        Dict with event_id, webhook_results, notification_id
    """
    event_id = generate_id("gevt_")

    # Emit to webhook subscribers
    webhook_results = await emit_event(event_type, {**payload, "event_id": event_id})

    result = {
        "event_id": event_id,
        "event_type": event_type,
        "webhook_deliveries": len(webhook_results),
        "notification_id": None,
    }

    # Create notification record if db session provided
    if db_session:
        try:
            from pearl.db.models.notification import NotificationRow

            notification_id = generate_id("notif_")
            notification = NotificationRow(
                notification_id=notification_id,
                recipient="all",
                project_id=payload.get("project_id"),
                event_type=event_type,
                title=EVENT_TITLES.get(event_type, event_type),
                body=_build_notification_body(event_type, payload),
                severity=EVENT_SEVERITY.get(event_type, "info"),
                read=False,
                link=_build_notification_link(event_type, payload),
                extra_data=payload,
            )
            db_session.add(notification)
            await db_session.flush()
            result["notification_id"] = notification_id
        except Exception as exc:
            logger.warning("Failed to create notification: %s", exc)

    return result


def _build_notification_body(event_type: str, payload: dict) -> str:
    """Build human-readable notification body."""
    project_id = payload.get("project_id", "unknown")

    if event_type == APPROVAL_CREATED:
        req_type = payload.get("request_type", "unknown")
        return f"Approval request ({req_type}) created for project {project_id}"
    elif event_type == APPROVAL_DECIDED:
        decision = payload.get("decision", "unknown")
        return f"Approval {decision} for project {project_id}"
    elif event_type == APPROVAL_NEEDS_INFO:
        return f"Reviewer requested more information for project {project_id}"
    elif event_type == PROMOTION_COMPLETED:
        src = payload.get("source_environment", "?")
        tgt = payload.get("target_environment", "?")
        return f"Project {project_id} promoted from {src} to {tgt}"
    elif event_type == FINDING_CRITICAL_DETECTED:
        count = payload.get("count", 1)
        return f"{count} critical finding(s) detected in project {project_id}"
    elif event_type == COST_THRESHOLD_REACHED:
        return f"Cost threshold reached for project {project_id}"
    return f"Governance event: {event_type}"


def _build_notification_link(event_type: str, payload: dict) -> str | None:
    """Build deep link to dashboard page."""
    project_id = payload.get("project_id")
    if event_type in (APPROVAL_CREATED, APPROVAL_DECIDED, APPROVAL_NEEDS_INFO):
        approval_id = payload.get("approval_request_id")
        if approval_id:
            return f"/approvals/{approval_id}"
    elif event_type == PROMOTION_COMPLETED:
        if project_id:
            return f"/projects/{project_id}/promotions"
    elif event_type == FINDING_CRITICAL_DETECTED:
        if project_id:
            return f"/projects/{project_id}/findings"
    return None
