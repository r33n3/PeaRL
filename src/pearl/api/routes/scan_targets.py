"""Scan target management and discovery routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError, ValidationError
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.scan_target_repo import ScanTargetRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Scan Targets"])


# --- Request/response models ---


class ScanHeartbeat(BaseModel):
    status: str  # succeeded, failed, in_progress
    scanned_at: datetime
    details: dict | None = None


# --- Helpers ---


async def _ensure_project_exists(project_id: str, db: AsyncSession):
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)
    return row


# --- Project-scoped routes (developer-facing) ---


@router.post("/projects/{project_id}/scan-targets", status_code=201)
async def register_scan_target(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    await _ensure_project_exists(project_id, db)
    repo = ScanTargetRepository(db)

    repo_url = body.get("repo_url")
    if not repo_url:
        raise ValidationError("repo_url is required")

    tool_type = body.get("tool_type", "mass")
    branch = body.get("branch", "main")

    # Check natural key uniqueness
    existing = await repo.get_by_natural_key(project_id, repo_url, tool_type, branch)
    if existing:
        raise ValidationError(
            f"Scan target already exists for {repo_url} / {tool_type} / {branch}",
            details={"scan_target_id": existing.scan_target_id},
        )

    scan_target_id = generate_id("scnt_")
    now = datetime.now(timezone.utc)

    row = await repo.create(
        scan_target_id=scan_target_id,
        project_id=project_id,
        repo_url=repo_url,
        branch=branch,
        tool_type=tool_type,
        scan_frequency=body.get("scan_frequency", "daily"),
        status="active",
        environment_scope=body.get("environment_scope"),
        labels=body.get("labels"),
    )

    await db.commit()

    return {
        "scan_target_id": row.scan_target_id,
        "project_id": row.project_id,
        "repo_url": row.repo_url,
        "branch": row.branch,
        "tool_type": row.tool_type,
        "scan_frequency": row.scan_frequency,
        "status": row.status,
        "environment_scope": row.environment_scope,
        "labels": row.labels,
    }


@router.get("/projects/{project_id}/scan-targets", status_code=200)
async def list_scan_targets(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _ensure_project_exists(project_id, db)
    repo = ScanTargetRepository(db)
    rows = await repo.list_by_project(project_id)
    return [
        {
            "scan_target_id": r.scan_target_id,
            "project_id": r.project_id,
            "repo_url": r.repo_url,
            "branch": r.branch,
            "tool_type": r.tool_type,
            "scan_frequency": r.scan_frequency,
            "status": r.status,
            "environment_scope": r.environment_scope,
            "labels": r.labels,
            "last_scanned_at": r.last_scanned_at.isoformat() if r.last_scanned_at else None,
            "last_scan_status": r.last_scan_status,
        }
        for r in rows
    ]


@router.put("/projects/{project_id}/scan-targets/{scan_target_id}", status_code=200)
async def update_scan_target(
    project_id: str,
    scan_target_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ScanTargetRepository(db)
    row = await repo.get(scan_target_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("ScanTarget", scan_target_id)

    updates = {}
    for field in ("branch", "scan_frequency", "status", "environment_scope", "labels"):
        if field in body:
            updates[field] = body[field]

    if updates:
        await repo.update(row, **updates)
        await db.commit()

    return {
        "scan_target_id": row.scan_target_id,
        "project_id": row.project_id,
        "repo_url": row.repo_url,
        "branch": row.branch,
        "tool_type": row.tool_type,
        "scan_frequency": row.scan_frequency,
        "status": row.status,
        "environment_scope": row.environment_scope,
        "labels": row.labels,
        "last_scanned_at": row.last_scanned_at.isoformat() if row.last_scanned_at else None,
        "last_scan_status": row.last_scan_status,
    }


@router.delete("/projects/{project_id}/scan-targets/{scan_target_id}", status_code=200)
async def delete_scan_target(
    project_id: str,
    scan_target_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete: sets status to disabled."""
    repo = ScanTargetRepository(db)
    row = await repo.get(scan_target_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("ScanTarget", scan_target_id)

    await repo.update(row, status="disabled")
    await db.commit()

    return {"scan_target_id": row.scan_target_id, "status": "disabled"}


# --- Tool-facing routes (cross-project) ---


@router.get("/scan-targets", status_code=200)
async def discover_scan_targets(
    tool_type: str = Query(..., description="Tool type to discover targets for"),
    status: str = Query("active", description="Filter by status"),
    project_id: str | None = Query(None, description="Optionally scope to a project"),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Discovery endpoint: tools call this to find what repos to scan."""
    repo = ScanTargetRepository(db)

    if project_id:
        all_rows = await repo.list_by_project(project_id)
        rows = [r for r in all_rows if r.tool_type == tool_type and r.status == status]
    else:
        rows = await repo.list_by_tool_type(tool_type, status)

    return [
        {
            "scan_target_id": r.scan_target_id,
            "project_id": r.project_id,
            "repo_url": r.repo_url,
            "branch": r.branch,
            "environment_scope": r.environment_scope,
            "labels": r.labels,
            "scan_frequency": r.scan_frequency,
            "last_scanned_at": r.last_scanned_at.isoformat() if r.last_scanned_at else None,
        }
        for r in rows
    ]


@router.post("/scan-targets/{scan_target_id}/heartbeat", status_code=200)
async def scan_heartbeat(
    scan_target_id: str,
    body: ScanHeartbeat,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Tool reports scan completion/status."""
    repo = ScanTargetRepository(db)
    row = await repo.get(scan_target_id)
    if not row:
        raise NotFoundError("ScanTarget", scan_target_id)

    await repo.update(
        row,
        last_scanned_at=body.scanned_at,
        last_scan_status=body.status,
    )
    await db.commit()

    return {
        "scan_target_id": row.scan_target_id,
        "last_scanned_at": row.last_scanned_at.isoformat() if row.last_scanned_at else None,
        "last_scan_status": row.last_scan_status,
    }
