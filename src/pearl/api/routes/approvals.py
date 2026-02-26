"""Approval workflow API routes."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import ConflictError, NotFoundError
from pearl.models.approval import ApprovalCommentCreate, ApprovalDecision, ApprovalRequest
from pearl.repositories.approval_comment_repo import ApprovalCommentRepository
from pearl.repositories.approval_repo import ApprovalDecisionRepository, ApprovalRequestRepository
from pearl.repositories.exception_repo import ExceptionRepository
from pearl.services.id_generator import generate_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Approvals"])


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

    return request.model_dump(mode="json", exclude_none=True)


@router.post("/approvals/{approval_request_id}/decide")
async def decide_approval(
    approval_request_id: str,
    decision: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
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
        decided_by=decision.decided_by,
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
                    approved_by=[decision.decided_by],
                )

    await db.commit()

    return decision.model_dump(mode="json", exclude_none=True)


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
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "expires_at": a.expires_at.isoformat() if a.expires_at else None,
        }
        for a in approvals
        if a.status in ("pending", "needs_info")
    ]


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
