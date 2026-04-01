"""Workload Registry API routes.

Agents register on startup, send periodic heartbeats, and deregister on exit.
Workloads with no heartbeat for >5 minutes are auto-marked inactive on read.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.api.routes.stream import publish_event
from pearl.dependencies import get_db, get_redis, require_role
from pearl.errors.exceptions import ConflictError, NotFoundError
from pearl.repositories.workload_repo import WorkloadRepository
from pearl.services.id_generator import generate_id

router = APIRouter(prefix="/workloads", tags=["Workloads"])

_RequireOperator = Depends(require_role("operator", "service_account", "admin"))
_RequireViewer = Depends(require_role("viewer", "operator", "service_account", "reviewer", "admin"))


@router.post("/register", status_code=201)
async def register_workload(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: dict = _RequireOperator,
) -> dict:
    """Register a new SVID → task packet mapping."""
    repo = WorkloadRepository(db)

    svid = payload.get("svid")
    if not svid:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError("svid is required")

    existing = await repo.get_by_svid(svid)
    if existing is not None:
        raise ConflictError(f"SVID already registered: {svid}")

    now = datetime.now(timezone.utc)
    workload = await repo.create(
        workload_id=generate_id("wkld_"),
        svid=svid,
        task_packet_id=payload.get("task_packet_id", ""),
        allowance_profile_id=payload.get("allowance_profile_id"),
        agent_id=payload.get("agent_id"),
        registered_at=now,
        last_seen_at=now,
        status="active",
        metadata_=payload.get("metadata"),
    )
    await db.commit()

    redis = getattr(request.app.state, "redis", None)
    await publish_event(redis, "workload.registered", {
        "workload_id": workload.workload_id,
        "svid": workload.svid,
        "task_packet_id": workload.task_packet_id,
        "agent_id": workload.agent_id,
    })

    return {
        "workload_id": workload.workload_id,
        "svid": workload.svid,
        "status": workload.status,
        "registered_at": workload.registered_at.isoformat(),
    }


@router.post("/{svid:path}/heartbeat")
async def workload_heartbeat(
    svid: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = _RequireOperator,
) -> dict:
    """Update last_seen_at for an active workload."""
    repo = WorkloadRepository(db)
    workload = await repo.get_by_svid(svid)
    if workload is None or workload.status == "inactive":
        raise NotFoundError("Workload", svid)

    workload = await repo.update_heartbeat(workload)
    await db.commit()

    return {
        "workload_id": workload.workload_id,
        "last_seen_at": workload.last_seen_at.isoformat(),
    }


@router.delete("/{svid:path}")
async def deregister_workload(
    svid: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: dict = _RequireOperator,
) -> dict:
    """Deregister a workload by SVID."""
    repo = WorkloadRepository(db)
    workload = await repo.get_by_svid(svid)
    if workload is None:
        raise NotFoundError("Workload", svid)

    await repo.deactivate(workload)
    await db.commit()

    redis = getattr(request.app.state, "redis", None)
    await publish_event(redis, "workload.deregistered", {
        "workload_id": workload.workload_id,
        "svid": workload.svid,
    })

    return {"workload_id": workload.workload_id, "status": "inactive"}


@router.get("")
async def list_workloads(
    status: str = Query("active", pattern="^(active|inactive|all)$"),
    db: AsyncSession = Depends(get_db),
    _user: dict = _RequireViewer,
) -> list[dict]:
    """List workloads. Defaults to active only.

    ?status=active  — active workloads (default); auto-marks stale ones inactive
    ?status=inactive — inactive workloads
    ?status=all     — all workloads
    """
    repo = WorkloadRepository(db)

    if status == "active":
        rows = await repo.list_active()
        await db.commit()  # persist any stale→inactive transitions
    elif status == "inactive":
        all_rows = await repo.list_all()
        rows = [r for r in all_rows if r.status == "inactive"]
    else:  # all
        rows = await repo.list_all()

    return [
        {
            "workload_id": r.workload_id,
            "svid": r.svid,
            "task_packet_id": r.task_packet_id,
            "allowance_profile_id": r.allowance_profile_id,
            "agent_id": r.agent_id,
            "status": r.status,
            "registered_at": r.registered_at.isoformat() if r.registered_at else None,
            "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
        }
        for r in rows
    ]
