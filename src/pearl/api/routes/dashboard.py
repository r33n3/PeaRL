"""Dashboard aggregation API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.approval import ApprovalRequestRow
from pearl.db.models.environment_profile import EnvironmentProfileRow
from pearl.db.models.finding import FindingRow
from pearl.db.models.governance_telemetry import ClientAuditEventRow, ClientCostEntryRow
from pearl.db.models.project import ProjectRow
from pearl.db.models.promotion import PromotionEvaluationRow, PromotionHistoryRow
from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.approval_comment_repo import ApprovalCommentRepository
from pearl.repositories.approval_repo import ApprovalRequestRepository
from pearl.repositories.notification_repo import NotificationRepository

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/projects")
async def dashboard_projects(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Portfolio view — all projects with status summary."""
    result = await db.execute(select(ProjectRow))
    projects = list(result.scalars().all())

    # Bulk-fetch environment profiles (avoid N+1)
    env_result = await db.execute(select(EnvironmentProfileRow))
    env_profiles = {ep.project_id: ep.environment for ep in env_result.scalars().all()}

    summaries = []
    for p in projects:
        # Count pending approvals
        approval_stmt = select(func.count()).select_from(ApprovalRequestRow).where(
            ApprovalRequestRow.project_id == p.project_id,
            ApprovalRequestRow.status.in_(["pending", "needs_info"]),
        )
        pending_count = (await db.execute(approval_stmt)).scalar() or 0

        # Count open findings by severity
        finding_stmt = select(
            FindingRow.severity, func.count()
        ).where(
            FindingRow.project_id == p.project_id,
            FindingRow.status == "open",
        ).group_by(FindingRow.severity)
        finding_result = await db.execute(finding_stmt)
        findings_by_severity = {row[0]: row[1] for row in finding_result.all()}

        # Latest evaluation
        eval_stmt = select(PromotionEvaluationRow).where(
            PromotionEvaluationRow.project_id == p.project_id
        ).order_by(PromotionEvaluationRow.created_at.desc()).limit(1)
        latest_eval = (await db.execute(eval_stmt)).scalar_one_or_none()

        summaries.append({
            "project_id": p.project_id,
            "name": p.name,
            "environment": env_profiles.get(p.project_id),
            "pending_approvals": pending_count,
            "findings_by_severity": findings_by_severity,
            "total_open_findings": sum(findings_by_severity.values()),
            "gate_status": latest_eval.status if latest_eval else None,
            "gate_progress_pct": latest_eval.progress_pct if latest_eval else 0.0,
        })

    return summaries


@router.get("/projects/{project_id}/overview")
async def dashboard_project_overview(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Single project overview — findings, gates, cost, activity."""
    # Verify project exists
    proj_stmt = select(ProjectRow).where(ProjectRow.project_id == project_id)
    project = (await db.execute(proj_stmt)).scalar_one_or_none()
    if not project:
        raise NotFoundError("Project", project_id)

    # Current environment
    env_stmt = select(EnvironmentProfileRow).where(
        EnvironmentProfileRow.project_id == project_id
    )
    env_profile = (await db.execute(env_stmt)).scalar_one_or_none()

    # Findings by severity
    finding_stmt = select(
        FindingRow.severity, func.count()
    ).where(
        FindingRow.project_id == project_id,
        FindingRow.status == "open",
    ).group_by(FindingRow.severity)
    findings_by_severity = {r[0]: r[1] for r in (await db.execute(finding_stmt)).all()}

    # Latest evaluation
    eval_stmt = select(PromotionEvaluationRow).where(
        PromotionEvaluationRow.project_id == project_id
    ).order_by(PromotionEvaluationRow.created_at.desc()).limit(1)
    latest_eval = (await db.execute(eval_stmt)).scalar_one_or_none()

    # Cost summary
    cost_stmt = select(func.sum(ClientCostEntryRow.cost_usd)).where(
        ClientCostEntryRow.project_id == project_id
    )
    total_cost = (await db.execute(cost_stmt)).scalar() or 0.0

    # Pending approvals
    approval_repo = ApprovalRequestRepository(db)
    all_approvals = await approval_repo.list_by_project(project_id)
    pending = [a for a in all_approvals if a.status in ("pending", "needs_info")]

    # Recent activity (audit events)
    activity_stmt = select(ClientAuditEventRow).where(
        ClientAuditEventRow.project_id == project_id
    ).order_by(ClientAuditEventRow.created_at.desc()).limit(20)
    activities = list((await db.execute(activity_stmt)).scalars().all())

    # Promotion history
    history_stmt = select(PromotionHistoryRow).where(
        PromotionHistoryRow.project_id == project_id
    ).order_by(PromotionHistoryRow.promoted_at.desc()).limit(10)
    history = list((await db.execute(history_stmt)).scalars().all())

    return {
        "project_id": project_id,
        "name": project.name,
        "environment": env_profile.environment if env_profile else None,
        "findings_by_severity": findings_by_severity,
        "total_open_findings": sum(findings_by_severity.values()),
        "gate_status": latest_eval.status if latest_eval else None,
        "gate_progress_pct": latest_eval.progress_pct if latest_eval else 0.0,
        "gate_passed": latest_eval.passed_count if latest_eval else 0,
        "gate_total": latest_eval.total_count if latest_eval else 0,
        "total_cost_usd": round(total_cost, 4),
        "pending_approvals": [
            {
                "approval_request_id": a.approval_request_id,
                "request_type": a.request_type,
                "status": a.status,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in pending
        ],
        "recent_activity": [
            {
                "event_type": a.event_type,
                "action": a.action,
                "actor": a.source,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activities
        ],
        "promotion_history": [
            {
                "history_id": h.history_id,
                "source_environment": h.source_environment,
                "target_environment": h.target_environment,
                "promoted_by": h.promoted_by,
                "promoted_at": h.promoted_at.isoformat() if h.promoted_at else None,
            }
            for h in history
        ],
    }


@router.get("/approvals/pending")
async def dashboard_pending_approvals(
    project_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Pending approvals across all projects."""
    repo = ApprovalRequestRepository(db)
    if project_id:
        all_approvals = await repo.list_by_project(project_id)
    else:
        pending = await repo.list_by_status("pending")
        needs_info = await repo.list_by_status("needs_info")
        all_approvals = pending + needs_info

    return [
        {
            "approval_request_id": a.approval_request_id,
            "project_id": a.project_id,
            "environment": a.environment,
            "request_type": a.request_type,
            "status": a.status,
            "request_data": a.request_data,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        }
        for a in all_approvals
        if a.status in ("pending", "needs_info")
    ]


@router.get("/approvals/{approval_request_id}/thread")
async def dashboard_approval_thread(
    approval_request_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Approval with full conversation thread."""
    req_repo = ApprovalRequestRepository(db)
    approval = await req_repo.get(approval_request_id)
    if not approval:
        raise NotFoundError("Approval request", approval_request_id)

    comment_repo = ApprovalCommentRepository(db)
    comments = await comment_repo.list_by_approval(approval_request_id)

    return {
        "approval": {
            "approval_request_id": approval.approval_request_id,
            "project_id": approval.project_id,
            "environment": approval.environment,
            "request_type": approval.request_type,
            "status": approval.status,
            "request_data": approval.request_data,
            "created_at": approval.created_at.isoformat() if approval.created_at else None,
        },
        "comments": [
            {
                "comment_id": c.comment_id,
                "author": c.author,
                "author_role": c.author_role,
                "content": c.content,
                "comment_type": c.comment_type,
                "attachments": c.attachments,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in comments
        ],
    }


@router.get("/notifications")
async def dashboard_notifications(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """User's unread notifications."""
    repo = NotificationRepository(db)
    notifications = await repo.list_unread()
    return [
        {
            "notification_id": n.notification_id,
            "project_id": n.project_id,
            "event_type": n.event_type,
            "title": n.title,
            "body": n.body,
            "severity": n.severity,
            "read": n.read,
            "link": n.link,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]


@router.post("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Mark a notification as read."""
    repo = NotificationRepository(db)
    success = await repo.mark_read(notification_id)
    if not success:
        raise NotFoundError("Notification", notification_id)
    await db.commit()
    return {"notification_id": notification_id, "read": True}
