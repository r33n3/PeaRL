"""Dashboard aggregation API routes."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.app_spec import AppSpecRow
from pearl.db.models.approval import ApprovalDecisionRow, ApprovalRequestRow
from pearl.db.models.environment_profile import EnvironmentProfileRow
from pearl.db.models.exception import ExceptionRecordRow as ExceptionRow
from pearl.db.models.finding import FindingRow
from pearl.db.models.governance_telemetry import ClientAuditEventRow, ClientCostEntryRow
from pearl.db.models.org_baseline import OrgBaselineRow
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
            "bu_id": p.bu_id,
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

    # Behavioral drift trend finding count (open)
    drift_trend_count = (await db.execute(
        select(func.count()).select_from(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.category == "drift_trend",
            FindingRow.status == "open",
        )
    )).scalar() or 0

    # Latest evaluation
    eval_stmt = select(PromotionEvaluationRow).where(
        PromotionEvaluationRow.project_id == project_id
    ).order_by(PromotionEvaluationRow.created_at.desc()).limit(1)
    latest_eval = (await db.execute(eval_stmt)).scalar_one_or_none()

    # Promotion history
    history_stmt = select(PromotionHistoryRow).where(
        PromotionHistoryRow.project_id == project_id
    ).order_by(PromotionHistoryRow.promoted_at.desc()).limit(10)
    history = list((await db.execute(history_stmt)).scalars().all())

    # Cost summary — windowed to project compliance lifecycle
    window_start = project.created_at
    last_promotion = history[0].promoted_at if history else None  # history is desc order
    window_end = last_promotion if last_promotion else datetime.now(timezone.utc)
    cost_stmt = select(func.sum(ClientCostEntryRow.cost_usd)).where(
        ClientCostEntryRow.project_id == project_id,
        ClientCostEntryRow.timestamp >= window_start,
        ClientCostEntryRow.timestamp <= window_end,
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

    return {
        "project_id": project_id,
        "name": project.name,
        "environment": env_profile.environment if env_profile else None,
        "findings_by_severity": findings_by_severity,
        "total_open_findings": sum(findings_by_severity.values()),
        "behavioral_drift_trend_count": drift_trend_count,
        "gate_status": latest_eval.status if latest_eval else None,
        "gate_progress_pct": latest_eval.progress_pct if latest_eval else 0.0,
        "gate_passed": latest_eval.passed_count if latest_eval else 0,
        "gate_total": latest_eval.total_count if latest_eval else 0,
        "total_cost_usd": round(total_cost, 4),
        "cost_window_start": window_start.isoformat() if window_start else None,
        "cost_window_end": window_end.isoformat(),
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


@router.get("/projects/{project_id}/governance")
async def dashboard_project_governance(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Project governance outcomes — MTTR, gate history, pipeline timing, cost."""
    now = datetime.now(timezone.utc)

    # Verify project exists
    proj_stmt = select(ProjectRow).where(ProjectRow.project_id == project_id)
    project = (await db.execute(proj_stmt)).scalar_one_or_none()
    if not project:
        raise NotFoundError("Project", project_id)

    # --- Finding resolution (all-time) ---
    resolved_rows = list((await db.execute(
        select(FindingRow.detected_at, FindingRow.resolved_at).where(
            FindingRow.project_id == project_id,
            FindingRow.status == "resolved",
            FindingRow.resolved_at.isnot(None),
        )
    )).all())
    mttr_days = None
    if resolved_rows:
        durations = [
            (row[1] - row[0]).total_seconds() / 86400
            for row in resolved_rows
            if row[0] and row[1]
        ]
        if durations:
            mttr_days = round(sum(durations) / len(durations), 1)

    findings_resolved_total = len(resolved_rows)
    open_count = (await db.execute(
        select(func.count()).select_from(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.status == "open",
        )
    )).scalar() or 0

    resolution_rate_pct = None
    total_findings = findings_resolved_total + open_count
    if total_findings > 0:
        resolution_rate_pct = round(findings_resolved_total / total_findings * 100, 1)

    # --- Gate history ---
    eval_rows = list((await db.execute(
        select(PromotionEvaluationRow).where(
            PromotionEvaluationRow.project_id == project_id
        ).order_by(PromotionEvaluationRow.created_at.asc())
    )).scalars().all())

    gate_attempts_total = len(eval_rows)
    gate_pass_attempts = sum(1 for e in eval_rows if e.status == "passed")
    gate_fail_attempts = sum(1 for e in eval_rows if e.status == "failed")
    last_gate_status = eval_rows[-1].status if eval_rows else None
    gate_first_pass_attempt = None
    for i, e in enumerate(eval_rows):
        if e.status == "passed":
            gate_first_pass_attempt = i + 1
            break

    # --- Pipeline timing ---
    days_in_pipeline = (
        (now - project.created_at).total_seconds() / 86400
        if project.created_at else None
    )

    history_rows = list((await db.execute(
        select(PromotionHistoryRow).where(
            PromotionHistoryRow.project_id == project_id
        ).order_by(PromotionHistoryRow.promoted_at.asc())
    )).scalars().all())

    # Build per-environment entry/exit times
    env_entry: dict[str, datetime] = {}
    env_exit: dict[str, datetime | None] = {}
    if project.created_at:
        env_entry["sandbox"] = project.created_at
    for h in history_rows:
        if h.promoted_at:
            env_exit[h.source_environment] = h.promoted_at
            env_entry[h.target_environment] = h.promoted_at

    # Current environment
    env_profile_row = (await db.execute(
        select(EnvironmentProfileRow).where(EnvironmentProfileRow.project_id == project_id)
    )).scalar_one_or_none()
    current_env = env_profile_row.environment if env_profile_row else "sandbox"
    env_exit.setdefault(current_env, None)

    env_chain = ["sandbox", "dev", "preprod", "prod"]
    time_per_environment = []
    for env in env_chain:
        if env not in env_entry:
            continue
        entry_at = env_entry[env]
        exit_at = env_exit.get(env)
        days = (
            (exit_at - entry_at).total_seconds() / 86400
            if exit_at else (now - entry_at).total_seconds() / 86400
        )
        time_per_environment.append({
            "environment": env,
            "days": round(days, 1),
            "entry_at": entry_at.isoformat(),
            "exit_at": exit_at.isoformat() if exit_at else None,
        })

    # Days in current environment
    if history_rows and history_rows[-1].promoted_at:
        days_in_current_env: float | None = round(
            (now - history_rows[-1].promoted_at).total_seconds() / 86400, 1
        )
    else:
        days_in_current_env = round(days_in_pipeline, 1) if days_in_pipeline is not None else None

    # --- Gate decision latency ---
    latency_rows = list((await db.execute(
        select(ApprovalRequestRow.created_at, ApprovalDecisionRow.decided_at).join(
            ApprovalDecisionRow,
            ApprovalDecisionRow.approval_request_id == ApprovalRequestRow.approval_request_id,
        ).where(
            ApprovalRequestRow.project_id == project_id,
        )
    )).all())
    gate_decision_latency_days = None
    if latency_rows:
        latencies = [
            (row[1] - row[0]).total_seconds() / 86400
            for row in latency_rows
            if row[0] and row[1]
        ]
        if latencies:
            gate_decision_latency_days = round(sum(latencies) / len(latencies), 2)

    # --- Cost — windowed to project compliance lifecycle ---
    gov_window_start = project.created_at
    last_promotion_ts = history_rows[-1].promoted_at if history_rows else None
    gov_window_end = last_promotion_ts if last_promotion_ts else datetime.now(timezone.utc)
    total_cost = round(
        (await db.execute(
            select(func.sum(ClientCostEntryRow.cost_usd)).where(
                ClientCostEntryRow.project_id == project_id,
                ClientCostEntryRow.timestamp >= gov_window_start,
                ClientCostEntryRow.timestamp <= gov_window_end,
            )
        )).scalar() or 0.0,
        4,
    )

    # --- Exception decisions ---
    exc_approved = (await db.execute(
        select(func.count()).select_from(ExceptionRow).where(
            ExceptionRow.project_id == project_id,
            ExceptionRow.status.in_(["active", "expired", "revoked"]),
        )
    )).scalar() or 0

    exc_rejected = (await db.execute(
        select(func.count()).select_from(ExceptionRow).where(
            ExceptionRow.project_id == project_id,
            ExceptionRow.status == "rejected",
        )
    )).scalar() or 0

    exc_pending = (await db.execute(
        select(func.count()).select_from(ExceptionRow).where(
            ExceptionRow.project_id == project_id,
            ExceptionRow.status == "pending",
        )
    )).scalar() or 0

    # Time to approve: start_at - created_at for approved exceptions
    approved_timing = list((await db.execute(
        select(ExceptionRow.created_at, ExceptionRow.start_at).where(
            ExceptionRow.project_id == project_id,
            ExceptionRow.status.in_(["active", "expired", "revoked"]),
            ExceptionRow.start_at.isnot(None),
        )
    )).all())
    avg_time_to_approve_days = None
    if approved_timing:
        durations = [
            (row[1] - row[0]).total_seconds() / 86400
            for row in approved_timing
            if row[0] and row[1]
        ]
        if durations:
            avg_time_to_approve_days = round(sum(durations) / len(durations), 1)

    # Time to reject: updated_at - created_at for rejected exceptions
    rejected_timing = list((await db.execute(
        select(ExceptionRow.created_at, ExceptionRow.updated_at).where(
            ExceptionRow.project_id == project_id,
            ExceptionRow.status == "rejected",
        )
    )).all())
    avg_time_to_reject_days = None
    if rejected_timing:
        durations = [
            (row[1] - row[0]).total_seconds() / 86400
            for row in rejected_timing
            if row[0] and row[1]
        ]
        if durations:
            avg_time_to_reject_days = round(sum(durations) / len(durations), 1)

    return {
        "mttr_days": mttr_days,
        "findings_resolved_total": findings_resolved_total,
        "findings_open_total": open_count,
        "resolution_rate_pct": resolution_rate_pct,
        "gate_attempts_total": gate_attempts_total,
        "gate_pass_attempts": gate_pass_attempts,
        "gate_fail_attempts": gate_fail_attempts,
        "last_gate_status": last_gate_status,
        "gate_first_pass_attempt": gate_first_pass_attempt,
        "days_in_pipeline": round(days_in_pipeline, 1) if days_in_pipeline is not None else None,
        "days_in_current_env": days_in_current_env,
        "time_per_environment": time_per_environment,
        "gate_decision_latency_days": gate_decision_latency_days,
        "total_cost_usd": total_cost,
        "cost_window_start": gov_window_start.isoformat() if gov_window_start else None,
        "cost_window_end": gov_window_end.isoformat(),
        "exceptions_approved": exc_approved,
        "exceptions_rejected": exc_rejected,
        "exceptions_pending": exc_pending,
        "avg_time_to_approve_days": avg_time_to_approve_days,
        "avg_time_to_reject_days": avg_time_to_reject_days,
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


@router.get("/policy/baselines")
async def dashboard_policy_baselines(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """Portfolio-wide baseline status — one entry per project with baseline config and exception counts."""
    # All projects
    projects = list((await db.execute(select(ProjectRow))).scalars().all())

    # Bulk-fetch project-specific baselines (project_id IS NOT NULL) keyed by project_id
    project_baseline_rows = list((await db.execute(
        select(OrgBaselineRow).where(OrgBaselineRow.project_id.isnot(None))
    )).scalars().all())
    baselines: dict[str, OrgBaselineRow] = {row.project_id: row for row in project_baseline_rows}

    # Bulk-fetch BU-level baselines keyed by bu_id
    from pearl.db.models.business_unit import BusinessUnitRow
    bu_baseline_rows = list((await db.execute(
        select(OrgBaselineRow)
        .where(OrgBaselineRow.bu_id.isnot(None))
        .where(OrgBaselineRow.project_id.is_(None))
    )).scalars().all())
    bu_baselines: dict[str, OrgBaselineRow] = {row.bu_id: row for row in bu_baseline_rows}

    # Bulk-fetch BU names keyed by bu_id
    bu_rows = list((await db.execute(select(BusinessUnitRow))).scalars().all())
    bu_names: dict[str, str] = {bu.bu_id: bu.name for bu in bu_rows}

    # Fetch org-wide baseline (project_id IS NULL, bu_id IS NULL) for fallback
    org_baseline_row = (await db.execute(
        select(OrgBaselineRow)
        .where(OrgBaselineRow.project_id.is_(None))
        .where(OrgBaselineRow.bu_id.is_(None))
        .limit(1)
    )).scalar_one_or_none()

    # Bulk-fetch app specs keyed by project_id (for scope exclusions)
    app_spec_rows = list((await db.execute(select(AppSpecRow))).scalars().all())
    app_specs: dict[str, AppSpecRow] = {row.project_id: row for row in app_spec_rows}

    # Determine mandatory controls from org baseline environment_requirements
    mandatory_controls: list[str] = []
    if org_baseline_row and org_baseline_row.environment_defaults:
        env_reqs = org_baseline_row.environment_defaults.get("environment_requirements", {})
        if isinstance(env_reqs, dict):
            seen: set[str] = set()
            for env_list in env_reqs.values():
                if isinstance(env_list, list):
                    for ctrl in env_list:
                        if ctrl not in seen:
                            mandatory_controls.append(ctrl)
                            seen.add(ctrl)

    # Bulk-fetch exception counts by project_id and status
    exc_rows = list((await db.execute(
        select(ExceptionRow.project_id, ExceptionRow.status, func.count())
        .group_by(ExceptionRow.project_id, ExceptionRow.status)
    )).all())
    exc_by_project: dict[str, dict[str, int]] = {}
    for pid, status, cnt in exc_rows:
        exc_by_project.setdefault(pid, {})[status] = cnt

    # Bulk-fetch exception details for active/pending (for card display)
    exc_detail_rows = list((await db.execute(
        select(ExceptionRow).where(
            ExceptionRow.status.in_(["active", "pending"])
        ).order_by(ExceptionRow.project_id, ExceptionRow.created_at.desc())
    )).scalars().all())
    exc_details_by_project: dict[str, list] = {}
    for e in exc_detail_rows:
        exc_details_by_project.setdefault(e.project_id, []).append({
            "exception_id": e.exception_id,
            "status": e.status,
            "rationale": e.rationale,
            "scope": e.scope,
            "expires_at": e.expires_at.isoformat() if e.expires_at else None,
        })

    result = []
    for p in projects:
        project_baseline = baselines.get(p.project_id)
        bu_baseline = bu_baselines.get(p.bu_id) if p.bu_id else None
        # 3-tier resolution: project → BU → org-wide
        if project_baseline is not None:
            baseline = project_baseline
            baseline_source = "project"
        elif bu_baseline is not None:
            baseline = bu_baseline
            baseline_source = "bu"
        elif org_baseline_row is not None:
            baseline = org_baseline_row
            baseline_source = "org"
        else:
            baseline = None
            baseline_source = "org"
        inherits_org_baseline = project_baseline is None and org_baseline_row is not None
        counts = exc_by_project.get(p.project_id, {})

        # Summarise which control domains are enabled (any true value in each domain)
        domain_summary: dict[str, dict] = {}
        if baseline and baseline.defaults:
            for domain, controls in baseline.defaults.items():
                if isinstance(controls, dict):
                    enabled = sum(1 for v in controls.values() if v is True)
                    total = len(controls)
                    domain_summary[domain] = {"enabled": enabled, "total": total}

        # Scope exclusions from app spec
        app_spec = app_specs.get(p.project_id)
        raw_exclusions: list[str] = []
        if app_spec and app_spec.full_spec:
            raw_exclusions = app_spec.full_spec.get("policy_scope_exclusions") or []

        result.append({
            "project_id": p.project_id,
            "name": p.name,
            "baseline_configured": baseline is not None,
            "baseline_id": baseline.baseline_id if baseline else None,
            "org_name": baseline.org_name if baseline else None,
            "domain_summary": domain_summary,
            "active_exceptions": counts.get("active", 0),
            "pending_exceptions": counts.get("pending", 0),
            "exceptions": exc_details_by_project.get(p.project_id, []),
            "inherits_org_baseline": inherits_org_baseline,
            "scope_exclusions": raw_exclusions,
            "mandatory_controls": mandatory_controls,
            "bu_id": p.bu_id,
            "bu_name": bu_names.get(p.bu_id) if p.bu_id else None,
            "baseline_source": baseline_source,
        })

    return result


@router.get("/metrics")
async def dashboard_metrics(db: AsyncSession = Depends(get_db)) -> dict:
    """Portfolio-wide metrics: drift series, MTTR, MTTE, velocity, blocked projects."""
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    sixty_days_ago = now - timedelta(days=60)
    ninety_days_ago = now - timedelta(days=90)

    # --- Drift series: last 7 days (newest last) ---
    drift_series = []
    for i in range(6, -1, -1):
        day = (now - timedelta(days=i)).date()
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        new_count = (await db.execute(
            select(func.count()).select_from(FindingRow).where(
                FindingRow.detected_at >= day_start,
                FindingRow.detected_at < day_end,
            )
        )).scalar() or 0
        resolved_count = (await db.execute(
            select(func.count()).select_from(FindingRow).where(
                FindingRow.resolved_at >= day_start,
                FindingRow.resolved_at < day_end,
            )
        )).scalar() or 0
        drift_series.append({
            "date": day.isoformat(),
            "new": new_count,
            "resolved": resolved_count,
            "net": new_count - resolved_count,
        })

    # --- MTTR: avg(resolved_at - detected_at) for resolved findings last 30d ---
    resolved_rows = list((await db.execute(
        select(FindingRow.detected_at, FindingRow.resolved_at).where(
            FindingRow.status == "resolved",
            FindingRow.resolved_at.isnot(None),
            FindingRow.resolved_at >= thirty_days_ago,
        )
    )).all())
    mttr_days = None
    if resolved_rows:
        durations = [
            (row[1] - row[0]).total_seconds() / 86400
            for row in resolved_rows
            if row[0] and row[1]
        ]
        if durations:
            mttr_days = round(sum(durations) / len(durations), 1)

    # MTTR trend: compare current 30d vs prior 30d
    mttr_trend = "stable"
    if mttr_days is not None:
        prev_rows = list((await db.execute(
            select(FindingRow.detected_at, FindingRow.resolved_at).where(
                FindingRow.status == "resolved",
                FindingRow.resolved_at.isnot(None),
                FindingRow.resolved_at >= sixty_days_ago,
                FindingRow.resolved_at < thirty_days_ago,
            )
        )).all())
        if prev_rows:
            prev_durations = [
                (row[1] - row[0]).total_seconds() / 86400
                for row in prev_rows
                if row[0] and row[1]
            ]
            if prev_durations:
                prev_mttr = sum(prev_durations) / len(prev_durations)
                if mttr_days < prev_mttr * 0.9:
                    mttr_trend = "improving"
                elif mttr_days > prev_mttr * 1.1:
                    mttr_trend = "worsening"

    # --- MTTE: avg days between consecutive promotions per project (last 90d) ---
    history_rows = list((await db.execute(
        select(PromotionHistoryRow.project_id, PromotionHistoryRow.promoted_at).where(
            PromotionHistoryRow.promoted_at >= ninety_days_ago,
        ).order_by(PromotionHistoryRow.project_id, PromotionHistoryRow.promoted_at)
    )).all())
    mtte_gaps: list[float] = []
    by_project: dict[str, list] = {}
    for row in history_rows:
        by_project.setdefault(row[0], []).append(row[1])
    for timestamps in by_project.values():
        for j in range(1, len(timestamps)):
            if timestamps[j] and timestamps[j - 1]:
                gap = (timestamps[j] - timestamps[j - 1]).total_seconds() / 86400
                mtte_gaps.append(gap)
    mtte_days = round(sum(mtte_gaps) / len(mtte_gaps), 1) if mtte_gaps else None

    # --- Blocked projects: count projects where latest gate eval status = "failed" ---
    all_evals = list((await db.execute(
        select(
            PromotionEvaluationRow.project_id,
            PromotionEvaluationRow.status,
            PromotionEvaluationRow.created_at,
        ).order_by(PromotionEvaluationRow.project_id, PromotionEvaluationRow.created_at.desc())
    )).all())
    seen: set[str] = set()
    blocked_projects = 0
    for row in all_evals:
        pid, status = row[0], row[1]
        if pid not in seen:
            seen.add(pid)
            if status == "failed":
                blocked_projects += 1

    # --- Total PeaRL cost ---
    total_pearl_cost_usd = round(
        (await db.execute(select(func.sum(ClientCostEntryRow.cost_usd)))).scalar() or 0.0,
        2,
    )

    # --- Open findings ---
    open_sev = dict((await db.execute(
        select(FindingRow.severity, func.count()).where(
            FindingRow.status == "open",
        ).group_by(FindingRow.severity)
    )).all())
    open_findings_total = sum(open_sev.values())

    # --- 7-day velocity ---
    velocity_new_7d = (await db.execute(
        select(func.count()).select_from(FindingRow).where(
            FindingRow.detected_at >= seven_days_ago,
        )
    )).scalar() or 0
    velocity_resolved_7d = (await db.execute(
        select(func.count()).select_from(FindingRow).where(
            FindingRow.resolved_at.isnot(None),
            FindingRow.resolved_at >= seven_days_ago,
        )
    )).scalar() or 0

    return {
        "drift_series": drift_series,
        "mttr_days": mttr_days,
        "mttr_trend": mttr_trend,
        "mtte_days": mtte_days,
        "velocity_new_7d": velocity_new_7d,
        "velocity_resolved_7d": velocity_resolved_7d,
        "blocked_projects": blocked_projects,
        "open_findings_total": open_findings_total,
        "open_critical": open_sev.get("critical", 0),
        "open_high": open_sev.get("high", 0),
        "total_pearl_cost_usd": total_pearl_cost_usd,
    }


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
