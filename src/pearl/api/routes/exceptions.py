"""Policy exception API route."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id, RequireReviewer
from pearl.errors.exceptions import NotFoundError
from pearl.models.exception import ExceptionRecord
from pearl.repositories.exception_repo import ExceptionRepository

router = APIRouter(tags=["Exceptions"])


@router.get("/projects/{project_id}/exceptions", status_code=200)
async def list_project_exceptions(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = ExceptionRepository(db)
    exceptions = await repo.list_by_project(project_id)
    return [
        {
            "exception_id": e.exception_id,
            "project_id": e.project_id,
            "scope": e.scope,
            "status": e.status,
            "requested_by": e.requested_by,
            "rationale": e.rationale,
            "compensating_controls": e.compensating_controls,
            "approved_by": e.approved_by,
            "start_at": e.start_at.isoformat() if e.start_at else None,
            "expires_at": e.expires_at.isoformat() if e.expires_at else None,
            "created_at": e.created_at.isoformat() if hasattr(e, "created_at") and e.created_at else None,
        }
        for e in exceptions
    ]


@router.post("/exceptions", status_code=201)
async def create_exception(
    exception: ExceptionRecord,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    repo = ExceptionRepository(db)

    scope_dict = exception.scope.model_dump(mode="json", exclude_none=True) if exception.scope else None

    # Idempotent — return existing record if already created
    existing = await repo.get(exception.exception_id)
    if existing:
        return {
            "exception_id": existing.exception_id,
            "project_id": existing.project_id,
            "status": existing.status,
            "already_existed": True,
        }

    await repo.create(
        exception_id=exception.exception_id,
        project_id=exception.project_id,
        scope=scope_dict,
        status=exception.status,
        requested_by=exception.requested_by,
        rationale=exception.rationale,
        compensating_controls=exception.compensating_controls,
        approved_by=exception.approved_by,
        start_at=exception.start_at,
        expires_at=exception.expires_at,
        review_cadence_days=exception.review_cadence_days,
        trace_id=exception.trace_id,
    )
    await db.commit()

    return exception.model_dump(mode="json", exclude_none=True)


def _serialize_exception(e) -> dict:
    return {
        "exception_id": e.exception_id,
        "project_id": e.project_id,
        "scope": e.scope,
        "status": e.status,
        "requested_by": e.requested_by,
        "rationale": e.rationale,
        "compensating_controls": e.compensating_controls,
        "approved_by": e.approved_by,
        "start_at": e.start_at.isoformat() if e.start_at else None,
        "expires_at": e.expires_at.isoformat() if e.expires_at else None,
        "created_at": e.created_at.isoformat() if hasattr(e, "created_at") and e.created_at else None,
    }


@router.get("/exceptions/pending", status_code=200)
async def list_pending_exceptions(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return all exceptions with status 'pending' across all projects."""
    repo = ExceptionRepository(db)
    exceptions = await repo.list_pending()
    return [_serialize_exception(e) for e in exceptions]


class ExceptionDecision(BaseModel):
    decision: str  # "approve" | "reject"
    decided_by: str
    reason: str = ""


@router.post("/exceptions/{exception_id}/decide", status_code=200)
async def decide_exception(
    exception_id: str,
    body: ExceptionDecision,
    db: AsyncSession = Depends(get_db),
    _reviewer: dict = RequireReviewer,
) -> dict:
    """Approve or reject a pending exception directly (no linked approval request)."""
    repo = ExceptionRepository(db)
    exc = await repo.get(exception_id)
    if not exc:
        raise NotFoundError("Exception", exception_id)

    now = datetime.now(timezone.utc)
    if body.decision == "approve":
        exc.status = "active"
        exc.start_at = now
        exc.approved_by = [body.decided_by]
    elif body.decision == "reject":
        exc.status = "rejected"
    else:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError("decision must be 'approve' or 'reject'")

    await db.commit()
    return _serialize_exception(exc)
