"""Findings ingestion and query API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import REVIEWER_ROLES, get_current_user, get_db, get_trace_id
from pearl.security.anomaly_detector import detect_agp03_bulk_false_positive, emit_detection
from pearl.errors.exceptions import AuthorizationError, NotFoundError
from pearl.models.findings_ingest import FindingsIngestRequest, FindingsIngestResponse
from pearl.repositories.finding_repo import FindingBatchRepository, FindingRepository
from pearl.repositories.finding_resolution_repo import FindingResolutionRepository
from pearl.services.id_generator import generate_id
from pearl.workers.queue import enqueue_job

router = APIRouter(tags=["Findings"])


class FindingStatusUpdate(BaseModel):
    status: str  # "resolved", "false_positive", "accepted", "suppressed", "open"
    # Evidence fields — required when status="resolved"
    approval_mode: str | None = None   # "human" | "rescan"
    evidence_notes: str | None = None
    commit_sha: str | None = None
    pr_url: str | None = None
    test_run_id: str | None = None
    diff_summary: str | None = None
    resolved_by: str | None = None


class BulkStatusUpdate(BaseModel):
    finding_ids: list[str]
    status: str  # "resolved", "false_positive", "accepted", "suppressed", "open"


class ResolutionDecision(BaseModel):
    decided_by: str
    reason: str | None = None


class ResolutionRejection(BaseModel):
    decided_by: str
    rejection_reason: str


def _finding_to_dict(f) -> dict:
    """Convert a FindingRow to a frontend-friendly dict."""
    full = f.full_data or {}
    description = full.get("description", "")
    affected_files = full.get("affected_components", [])
    compliance_refs = full.get("compliance_refs")
    confidence = full.get("confidence")
    source_tool = ""
    if f.source and isinstance(f.source, dict):
        source_tool = f.source.get("tool_name", "")
    return {
        "finding_id": f.finding_id,
        "project_id": f.project_id,
        "title": f.title,
        "severity": f.severity,
        "status": f.status,
        "category": f.category,
        "environment": f.environment,
        "source_tool": source_tool,
        "description": description,
        "cwe_ids": f.cwe_ids,
        "cve_id": f.cve_id,
        "fix_available": f.fix_available,
        "affected_files": affected_files,
        "compliance_refs": compliance_refs,
        "confidence": confidence,
        "detected_at": f.detected_at.isoformat() if f.detected_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _resolution_to_dict(r) -> dict:
    """Convert a FindingResolutionRow to a dict."""
    return {
        "resolution_id": r.resolution_id,
        "finding_id": r.finding_id,
        "resolved_by": r.resolved_by,
        "approval_mode": r.approval_mode,
        "approval_status": r.approval_status,
        "evidence_notes": r.evidence_notes,
        "commit_sha": r.commit_sha,
        "pr_url": r.pr_url,
        "test_run_id": r.test_run_id,
        "diff_summary": r.diff_summary,
        "approved_by": r.approved_by,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "rejection_reason": r.rejection_reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


@router.get("/projects/{project_id}/findings")
async def list_findings(
    project_id: str,
    severity: str | None = Query(None),
    status: str | None = Query(None),
    category: str | None = Query(None),
    limit: int = Query(20, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List findings for a project with pagination, filters, and severity summary."""
    repo = FindingRepository(db)
    findings = await repo.list_by_project(
        project_id=project_id,
        severity=severity,
        status=status,
        category=category,
        limit=limit,
        offset=offset,
    )
    total = await repo.count_by_project(
        project_id=project_id,
        severity=severity,
        status=status,
        category=category,
    )
    severity_counts = await repo.severity_counts(project_id)
    return {
        "items": [_finding_to_dict(f) for f in findings],
        "total": total,
        "limit": limit,
        "offset": offset,
        "severity_counts": severity_counts,
    }


@router.patch("/projects/{project_id}/findings/{finding_id}/status")
async def update_finding_status(
    project_id: str,
    finding_id: str,
    body: FindingStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Update a finding's status (triage action)."""
    if body.status == "false_positive":
        if not set(current_user.get("roles", [])).intersection(REVIEWER_ROLES):
            raise AuthorizationError("Marking findings as false_positive requires reviewer role")

    repo = FindingRepository(db)
    finding = await repo.get(finding_id)
    if not finding or finding.project_id != project_id:
        raise NotFoundError("Finding", finding_id)

    if body.status == "resolved":
        # Transition to pending_resolution — evidence must be approved before final resolution
        finding.status = "pending_resolution"
        res_repo = FindingResolutionRepository(db)
        await res_repo.create(
            resolution_id=generate_id("fres"),
            finding_id=finding_id,
            project_id=project_id,
            resolved_by=body.resolved_by or current_user.get("sub", "unknown"),
            approval_mode=body.approval_mode or "human",
            approval_status="pending",
            evidence_notes=body.evidence_notes,
            commit_sha=body.commit_sha,
            pr_url=body.pr_url,
            test_run_id=body.test_run_id,
            diff_summary=body.diff_summary,
        )
    else:
        finding.status = body.status

    await db.commit()
    return {"finding_id": finding_id, "status": finding.status}


@router.get("/projects/{project_id}/findings/{finding_id}/resolution")
async def get_finding_resolution(
    project_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch the resolution record for a finding (audit trail)."""
    finding_repo = FindingRepository(db)
    finding = await finding_repo.get(finding_id)
    if not finding or finding.project_id != project_id:
        raise NotFoundError("Finding", finding_id)

    res_repo = FindingResolutionRepository(db)
    resolution = await res_repo.get_by_finding(finding_id)
    if not resolution:
        raise NotFoundError("FindingResolution", finding_id)

    return _resolution_to_dict(resolution)


@router.post("/projects/{project_id}/findings/{finding_id}/resolution/approve")
async def approve_finding_resolution(
    project_id: str,
    finding_id: str,
    body: ResolutionDecision,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Approve fix evidence — finding transitions to resolved."""
    if not set(current_user.get("roles", [])).intersection(REVIEWER_ROLES):
        raise AuthorizationError("Approving resolutions requires reviewer role")

    finding_repo = FindingRepository(db)
    finding = await finding_repo.get(finding_id)
    if not finding or finding.project_id != project_id:
        raise NotFoundError("Finding", finding_id)

    res_repo = FindingResolutionRepository(db)
    resolution = await res_repo.get_by_finding(finding_id)
    if not resolution:
        raise NotFoundError("FindingResolution", finding_id)

    now = datetime.now(timezone.utc)
    resolution.approval_status = "approved"
    resolution.approved_by = body.decided_by
    resolution.approved_at = now
    finding.status = "resolved"
    finding.resolved_at = now

    await db.commit()
    return {"finding_id": finding_id, "status": "resolved", "approval_status": "approved"}


@router.post("/projects/{project_id}/findings/{finding_id}/resolution/reject")
async def reject_finding_resolution(
    project_id: str,
    finding_id: str,
    body: ResolutionRejection,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Reject fix evidence — finding is reopened."""
    if not set(current_user.get("roles", [])).intersection(REVIEWER_ROLES):
        raise AuthorizationError("Rejecting resolutions requires reviewer role")

    finding_repo = FindingRepository(db)
    finding = await finding_repo.get(finding_id)
    if not finding or finding.project_id != project_id:
        raise NotFoundError("Finding", finding_id)

    res_repo = FindingResolutionRepository(db)
    resolution = await res_repo.get_by_finding(finding_id)
    if not resolution:
        raise NotFoundError("FindingResolution", finding_id)

    resolution.approval_status = "rejected"
    resolution.rejection_reason = body.rejection_reason
    finding.status = "open"

    await db.commit()
    return {"finding_id": finding_id, "status": "open", "approval_status": "rejected"}


@router.post("/projects/{project_id}/findings/bulk-status")
async def bulk_update_finding_status(
    project_id: str,
    body: BulkStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> dict:
    """Update status for multiple findings at once (bulk triage)."""
    if body.status == "false_positive":
        if not set(current_user.get("roles", [])).intersection(REVIEWER_ROLES):
            raise AuthorizationError("Marking findings as false_positive requires reviewer role")
        # AGP-03: detect bulk false_positive marking inline (no DB query needed)
        agp03 = detect_agp03_bulk_false_positive(
            finding_count=len(body.finding_ids),
            project_id=project_id,
            user_sub=current_user.get("sub", "unknown"),
        )
        if agp03:
            emit_detection(agp03)
    repo = FindingRepository(db)
    findings = await repo.get_by_ids(body.finding_ids)
    updated = 0
    for f in findings:
        if f.project_id == project_id:
            f.status = body.status
            updated += 1
    await db.commit()
    return {"updated_count": updated, "status": body.status}


@router.post("/findings/ingest", status_code=202)
async def ingest_findings(
    request: FindingsIngestRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    batch_id = request.source_batch.batch_id
    accepted = 0
    quarantined = 0
    finding_repo = FindingRepository(db)

    ingested_finding_ids: set[str] = set()

    for finding in request.findings:
        try:
            await finding_repo.create(
                finding_id=finding.finding_id,
                project_id=finding.project_id,
                environment=finding.environment,
                category=finding.category,
                severity=finding.severity,
                title=finding.title,
                source=finding.source.model_dump(mode="json"),
                full_data=finding.model_dump(mode="json", exclude_none=True),
                normalized=finding.normalized or False,
                detected_at=finding.detected_at,
                batch_id=batch_id,
                cvss_score=finding.cvss_score,
                cwe_ids=finding.cwe_ids,
                cve_id=finding.cve_id,
                status=finding.status,
                fix_available=finding.fix_available,
                score=finding.score,
                compliance_refs=finding.compliance_refs,
                verdict=finding.verdict,
                rai_eval_type=finding.rai_eval_type,
            )
            ingested_finding_ids.add(finding.finding_id)
            accepted += 1
        except Exception:
            quarantined += 1

    # Create batch record
    batch_repo = FindingBatchRepository(db)
    await batch_repo.create(
        batch_id=batch_id,
        source_system=request.source_batch.source_system,
        trust_label=request.source_batch.trust_label,
        accepted_count=accepted,
        quarantined_count=quarantined,
        normalized_count=accepted if request.options and request.options.normalize_on_ingest else 0,
    )

    # Rescan auto-approval: for each project in the batch, check pending rescan resolutions
    project_ids = {f.project_id for f in request.findings}
    res_repo = FindingResolutionRepository(db)
    now = datetime.now(timezone.utc)
    for pid in project_ids:
        pending = await res_repo.get_pending_rescan(pid)
        for resolution in pending:
            # If the finding is absent from this rescan batch → fix is confirmed
            if resolution.finding_id not in ingested_finding_ids:
                resolution.approval_status = "auto_approved"
                resolution.approved_by = "rescan"
                resolution.approved_at = now
                # Resolve the parent finding
                parent = await finding_repo.get(resolution.finding_id)
                if parent:
                    parent.status = "resolved"
                    parent.resolved_at = now

    # Enqueue normalization job if requested
    job_id = None
    if request.options and request.options.normalize_on_ingest:
        job = await enqueue_job(
            session=db,
            job_type="normalize_findings",
            project_id=request.findings[0].project_id if request.findings else None,
            trace_id=trace_id,
        )
        job_id = job.job_id

    await db.commit()

    response = FindingsIngestResponse(
        schema_version="1.1",
        batch_id=batch_id,
        accepted_count=accepted,
        quarantined_count=quarantined,
        normalized_count=accepted if request.options and request.options.normalize_on_ingest else 0,
        job_id=job_id,
        trace_id=trace_id,
        timestamp=datetime.now(timezone.utc),
    )
    return response.model_dump(mode="json", exclude_none=True)
