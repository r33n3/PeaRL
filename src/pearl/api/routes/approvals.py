"""Approval workflow API routes."""

import structlog
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id, RequireReviewer
from pearl.errors.exceptions import ConflictError, NotFoundError
from pearl.models.approval import ApprovalCommentCreate, ApprovalDecision, ApprovalRequest
from pearl.repositories.approval_comment_repo import ApprovalCommentRepository
from pearl.repositories.approval_repo import ApprovalDecisionRepository, ApprovalRequestRepository
from pearl.repositories.exception_repo import ExceptionRepository
from pearl.repositories.fairness_repo import AuditEventRepository
from pearl.services.id_generator import generate_id
from pearl.api.routes.stream import publish_event

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["Approvals"])


@router.get("/approvals/pending")
async def list_pending_approvals(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = ApprovalRequestRepository(db)
    if project_id:
        approvals = await repo.list_by_project(project_id)
    else:
        approvals = await repo.list_by_statuses(["pending", "needs_info"])
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
        for a in approvals
        if a.status in ("pending", "needs_info")
    ]


@router.post("/approvals/requests", status_code=201)
async def create_approval_request(
    request: ApprovalRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    repo = ApprovalRequestRepository(db)

    await repo.create(
        approval_request_id=request.approval_request_id,
        project_id=request.project_id,
        environment=request.environment,
        request_type=request.request_type,
        status=request.status,
        request_data=request.model_dump(mode="json", exclude_none=True),
        trace_id=request.trace_id,
        expires_at=request.expires_at,
    )
    await db.commit()

    # Dispatch notification for promotion gate approvals
    if request.request_type == "promotion_gate":
        await _dispatch_promotion_notification(request, db)

    return request.model_dump(mode="json", exclude_none=True)


@router.post("/approvals/{approval_request_id}/decide")
async def decide_approval(
    approval_request_id: str,
    decision: ApprovalDecision,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
    _reviewer: dict = RequireReviewer,
) -> dict:
    req_repo = ApprovalRequestRepository(db)
    approval = await req_repo.get(approval_request_id)
    if not approval:
        raise NotFoundError("Approval request", approval_request_id)

    if approval.status not in ("pending", "needs_info"):
        raise ConflictError(f"Approval request is already '{approval.status}'")

    # Update approval status
    new_status = "approved" if decision.decision == "approve" else "rejected"
    approval.status = new_status
    approval.request_data = {
        **approval.request_data,
        "status": new_status,
    }

    # Store decision record
    dec_repo = ApprovalDecisionRepository(db)
    await dec_repo.create(
        approval_request_id=approval_request_id,
        decision=decision.decision,
        decided_by=_reviewer.get("sub"),
        decider_role=decision.decider_role,
        reason=decision.reason,
        conditions=decision.conditions,
        decided_at=decision.decided_at,
        trace_id=decision.trace_id,
    )

    # If approving an exception request, activate the linked exception record
    if decision.decision == "approve" and approval.request_type == "exception":
        exc_id = (approval.request_data or {}).get("exception_id")
        if exc_id:
            exc_repo = ExceptionRepository(db)
            exc = await exc_repo.get(exc_id)
            if exc:
                now = datetime.now(timezone.utc)
                await exc_repo.update(
                    exc,
                    status="active",
                    start_at=now,
                    approved_by=[_reviewer.get("sub")],
                )

    # If approving a promotion gate, write promotion history and advance the project environment
    if decision.decision == "approve" and approval.request_type == "promotion_gate":
        from sqlalchemy import select, func
        from pearl.db.models.finding import FindingRow
        from pearl.repositories.promotion_repo import PromotionHistoryRepository, PromotionGateRepository
        from pearl.repositories.project_repo import ProjectRepository

        req_data = approval.request_data or {}
        source_env = req_data.get("source_environment") or approval.environment or "unknown"
        target_env = req_data.get("target_environment") or req_data.get("environment") or "unknown"
        evaluation_id = req_data.get("evaluation_id", approval_request_id)
        now = datetime.now(timezone.utc)
        history_repo = PromotionHistoryRepository(db)
        await history_repo.create(
            history_id=generate_id("hist_"),
            project_id=approval.project_id,
            source_environment=source_env,
            target_environment=target_env,
            evaluation_id=evaluation_id,
            promoted_by=_reviewer.get("sub"),
            promoted_at=now,
            details={
                "approval_request_id": approval_request_id,
                "reason": decision.reason,
                "trace_id": trace_id,
            },
        )
        proj_repo = ProjectRepository(db)
        proj = await proj_repo.get(approval.project_id)
        if proj:
            await proj_repo.update(proj, current_environment=target_env)
        # Update environment_profile so the dashboard picks up the new environment
        from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
        ep_repo = EnvironmentProfileRepository(db)
        ep = await ep_repo.get_by_project(approval.project_id)
        if ep:
            ep.environment = target_env

        # Trust accumulation: increment pass_count on the gate (human approval only, not auto-pass)
        is_auto_pass = req_data.get("auto_pass", False)
        if not is_auto_pass:
            gate_id = req_data.get("gate_id")
            if gate_id:
                gate_repo = PromotionGateRepository(db)
                gate = await gate_repo.get(gate_id)
                if gate:
                    gate.pass_count = (gate.pass_count or 0) + 1
                    # Flip auto_pass if threshold reached and no open drift_trend findings
                    if not gate.auto_pass and gate.pass_count >= (gate.auto_pass_threshold or 5):
                        drift_count = (await db.execute(
                            select(func.count()).select_from(FindingRow).where(
                                FindingRow.project_id == approval.project_id,
                                FindingRow.category == "drift_trend",
                                FindingRow.status == "open",
                            )
                        )).scalar() or 0
                        if drift_count == 0:
                            gate.auto_pass = True

    await AuditEventRepository(db).append(
        event_id=generate_id("evt_"),
        resource_id=approval_request_id,
        action_type="approval.decided",
        actor=_reviewer.get("sub"),
        details={
            "decision": decision.decision,
            "project_id": approval.project_id,
            "environment": approval.environment,
            "request_type": approval.request_type,
        },
    )
    await db.commit()

    # Publish real-time event so dashboard and developer console update
    if request:
        redis = getattr(request.app.state, "redis", None)
        await publish_event(redis, "approval_decided", {
            "approval_request_id": approval_request_id,
            "project_id": approval.project_id,
            "request_type": approval.request_type,
            "decision": decision.decision,
            "new_status": new_status,
            "environment": approval.environment,
            "rule_type": (approval.request_data or {}).get("rule_type"),
        })

    return decision.model_dump(mode="json", exclude_none=True)


@router.post("/approvals/{approval_request_id}/comments", status_code=201)
async def add_approval_comment(
    approval_request_id: str,
    body: ApprovalCommentCreate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    req_repo = ApprovalRequestRepository(db)
    approval = await req_repo.get(approval_request_id)
    if not approval:
        raise NotFoundError("Approval request", approval_request_id)

    comment_repo = ApprovalCommentRepository(db)
    comment_id = generate_id("acmt_")
    await comment_repo.create(
        comment_id=comment_id,
        approval_request_id=approval_request_id,
        author=body.author,
        author_role=body.author_role,
        content=body.content,
        comment_type=body.comment_type,
        attachments=body.attachments,
    )

    if body.set_needs_info and approval.status == "pending":
        approval.status = "needs_info"

    await db.commit()

    # Optionally trigger evidence gathering when reviewer requests info
    if body.set_needs_info and body.comment_type == "question":
        try:
            from pearl.events.governance_events import emit_governance_event, APPROVAL_NEEDS_INFO
            await emit_governance_event(
                APPROVAL_NEEDS_INFO,
                {
                    "approval_request_id": approval_request_id,
                    "project_id": approval.project_id,
                    "question": body.content,
                    "requested_by": body.author,
                },
                db_session=db,
            )
            await db.commit()
        except Exception as exc:
            logger.warning("Failed to emit needs_info event: %s", exc)

    return {
        "comment_id": comment_id,
        "approval_request_id": approval_request_id,
        "author": body.author,
        "comment_type": body.comment_type,
        "status_changed": body.set_needs_info,
    }


@router.get("/approvals/{approval_request_id}/comments")
async def list_approval_comments(
    approval_request_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    req_repo = ApprovalRequestRepository(db)
    approval = await req_repo.get(approval_request_id)
    if not approval:
        raise NotFoundError("Approval request", approval_request_id)

    comment_repo = ApprovalCommentRepository(db)
    comments = await comment_repo.list_by_approval(approval_request_id)
    return [
        {
            "comment_id": c.comment_id,
            "approval_request_id": c.approval_request_id,
            "author": c.author,
            "author_role": c.author_role,
            "content": c.content,
            "comment_type": c.comment_type,
            "attachments": c.attachments,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in comments
    ]


async def _dispatch_promotion_notification(
    request: ApprovalRequest,
    db: AsyncSession,
) -> None:
    """Fire-and-forget notification to all enabled org-level sink adapters."""
    try:
        from pearl.repositories.integration_repo import IntegrationEndpointRepository
        from pearl.integrations.adapters import AVAILABLE_ADAPTERS, import_adapter
        from pearl.integrations.normalized import NormalizedNotification
        from pearl.integrations.config import AuthConfig, IntegrationEndpoint

        repo = IntegrationEndpointRepository(db)
        # Collect org-wide sinks (project_id IS NULL) that are enabled
        org_rows = await repo.list_org_wide()
        sinks = [
            r for r in org_rows
            if r.enabled and r.integration_type in ("sink", "bidirectional")
            and r.adapter_type in AVAILABLE_ADAPTERS
        ]

        req_data = request.request_data or {}
        target_env = (
            req_data.get("target_environment")
            or req_data.get("environment", "unknown")
        )
        passed = req_data.get("passed_count", 0)
        total = req_data.get("total_count", 0)
        blockers = req_data.get("blockers", [])
        pct = req_data.get("progress_pct", 0)

        subject = f"Promotion Gate: {request.project_id} \u2192 {target_env}"
        body = (
            f"{passed}/{total} gates passing ({pct}%).\n"
            f"{len(blockers)} blocker(s) require human review before promotion can proceed."
        )

        notification = NormalizedNotification(
            subject=subject,
            body=body,
            severity="high" if blockers else "low",
            project_id=request.project_id,
        )

        for sink in sinks:
            adapter_class = import_adapter(AVAILABLE_ADAPTERS[sink.adapter_type])
            adapter = adapter_class()
            if not hasattr(adapter, "push_notification"):
                continue
            try:
                endpoint = IntegrationEndpoint(
                    endpoint_id=sink.endpoint_id,
                    name=sink.name,
                    adapter_type=sink.adapter_type,
                    integration_type=sink.integration_type,
                    category=sink.category,
                    base_url=sink.base_url,
                    auth=AuthConfig(**(sink.auth_config or {})),
                    project_mapping=sink.project_mapping,
                    enabled=sink.enabled,
                    labels=sink.labels,
                )
                await adapter.push_notification(endpoint, notification)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "Notification dispatch failed for %s: %s", sink.endpoint_id, exc
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Promotion notification dispatch failed: %s", exc)
