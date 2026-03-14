"""Policy exception API routes."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id, RequireReviewer
from pearl.errors.exceptions import NotFoundError
from pearl.models.exception import ExceptionRecord
from pearl.repositories.exception_repo import ExceptionRepository

router = APIRouter(tags=["Exceptions"])


def _serialize_exception(e) -> dict:
    return {
        "exception_id": e.exception_id,
        "project_id": e.project_id,
        "exception_type": getattr(e, "exception_type", "exception"),
        "title": getattr(e, "title", None),
        "risk_rating": getattr(e, "risk_rating", None),
        "scope": e.scope,
        "status": e.status,
        "requested_by": e.requested_by,
        "rationale": e.rationale,
        "remediation_plan": getattr(e, "remediation_plan", None),
        "compensating_controls": e.compensating_controls,
        "approved_by": e.approved_by,
        "finding_ids": getattr(e, "finding_ids", None),
        "board_briefing": getattr(e, "board_briefing", None),
        "start_at": e.start_at.isoformat() if e.start_at else None,
        "expires_at": e.expires_at.isoformat() if e.expires_at else None,
        "created_at": e.created_at.isoformat() if hasattr(e, "created_at") and e.created_at else None,
        "updated_at": e.updated_at.isoformat() if hasattr(e, "updated_at") and e.updated_at else None,
    }


@router.get("/projects/{project_id}/exceptions", status_code=200)
async def list_project_exceptions(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = ExceptionRepository(db)
    exceptions = await repo.list_by_project(project_id)
    return [_serialize_exception(e) for e in exceptions]


@router.post("/exceptions", status_code=201)
async def create_exception(
    exception: ExceptionRecord,
    background_tasks: BackgroundTasks,
    request: Request,
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

    row = await repo.create(
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
        exception_type=exception.exception_type,
        title=exception.title,
        risk_rating=exception.risk_rating,
        remediation_plan=exception.remediation_plan,
        finding_ids=exception.finding_ids,
    )
    await db.commit()

    # AGP-01: detect rapid exception creation (background — post-response)
    session_factory = getattr(request.app.state, "db_session_factory", None)
    user_sub = getattr(request.state, "user", {}).get("sub", "unknown") if hasattr(request.state, "user") else "unknown"
    if session_factory:
        async def _agp01(sf=session_factory, pid=exception.project_id, sub=user_sub, tid=trace_id):
            from pearl.security.anomaly_detector import detect_agp01_exception_rate, emit_detection
            async with sf() as s:
                result = await detect_agp01_exception_rate(s, pid, sub, tid)
                if result:
                    emit_detection(result)
        background_tasks.add_task(_agp01)

    return exception.model_dump(mode="json", exclude_none=True)


@router.get("/exceptions/pending", status_code=200)
async def list_pending_exceptions(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return all exceptions with status 'pending' across all projects."""
    repo = ExceptionRepository(db)
    exceptions = await repo.list_pending()
    return [_serialize_exception(e) for e in exceptions]


@router.get("/exceptions", status_code=200)
async def list_all_exceptions(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return all exceptions across all projects (for governance overview)."""
    repo = ExceptionRepository(db)
    exceptions = await repo.list_all()
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


class ExceptionRevoke(BaseModel):
    revoked_by: str
    reason: str = ""


@router.post("/exceptions/{exception_id}/revoke", status_code=200)
async def revoke_exception(
    exception_id: str,
    body: ExceptionRevoke,
    db: AsyncSession = Depends(get_db),
    _reviewer: dict = RequireReviewer,
) -> dict:
    """Revoke an active exception — re-activates the gate rule it was covering."""
    repo = ExceptionRepository(db)
    exc = await repo.get(exception_id)
    if not exc:
        raise NotFoundError("Exception", exception_id)

    exc.status = "revoked"
    await db.commit()
    return _serialize_exception(exc)


class ExceptionBoardBriefingUpdate(BaseModel):
    board_briefing: str


@router.put("/exceptions/{exception_id}/board-briefing", status_code=200)
async def update_board_briefing(
    exception_id: str,
    body: ExceptionBoardBriefingUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Store (or update) the AI-generated board briefing for an exception."""
    repo = ExceptionRepository(db)
    exc = await repo.get(exception_id)
    if not exc:
        raise NotFoundError("Exception", exception_id)

    exc.board_briefing = body.board_briefing
    await db.commit()
    return _serialize_exception(exc)


@router.get("/exceptions/{exception_id}/audit-thread", status_code=200)
async def get_exception_audit_thread(
    exception_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a structured audit thread for a single exception record."""
    repo = ExceptionRepository(db)
    exc = await repo.get(exception_id)
    if not exc:
        raise NotFoundError("Exception", exception_id)

    events = []

    if exc.created_at:
        events.append({
            "event": "filed",
            "at": exc.created_at.isoformat(),
            "by": exc.requested_by,
            "detail": exc.rationale,
        })

    if exc.status in ("active",) and exc.start_at:
        events.append({
            "event": "approved",
            "at": exc.start_at.isoformat(),
            "by": (exc.approved_by or ["unknown"])[0],
            "detail": f"Exception approved — active until {exc.expires_at.isoformat() if exc.expires_at else 'no expiry'}",
        })

    if exc.status == "rejected":
        events.append({
            "event": "rejected",
            "at": exc.updated_at.isoformat() if exc.updated_at else None,
            "by": "reviewer",
            "detail": "Exception request was rejected.",
        })

    if exc.status == "revoked":
        events.append({
            "event": "revoked",
            "at": exc.updated_at.isoformat() if exc.updated_at else None,
            "by": "reviewer",
            "detail": "Exception was revoked — gate rule re-activated.",
        })

    return {
        "exception": _serialize_exception(exc),
        "audit_thread": events,
    }
