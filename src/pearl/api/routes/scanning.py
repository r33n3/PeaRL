"""Scanning API routes — trigger scans, get results, ingest security reviews."""

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError, ValidationError
from pearl.repositories.project_repo import ProjectRepository
from pearl.scanning.service import ScanningService

router = APIRouter(tags=["Scanning"])

_service = ScanningService()


# --- Request models ---


class ScanRequest(BaseModel):
    target_path: str
    analyzers: list[str] | None = None
    environment: str = "dev"


class SecurityReviewIngestRequest(BaseModel):
    markdown: str
    environment: str = "dev"


# --- Helpers ---


async def _ensure_project(project_id: str, db: AsyncSession):
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)
    return row


# --- Routes ---


@router.post("/projects/{project_id}/scans", status_code=202)
async def trigger_scan(
    project_id: str,
    body: ScanRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Trigger an AI security scan on a target path."""
    await _ensure_project(project_id, db)

    target = Path(body.target_path)
    if not target.exists():
        raise ValidationError(f"Target path does not exist: {body.target_path}")

    result = await _service.scan_and_ingest(
        target_path=target,
        project_id=project_id,
        session=db,
        analyzers=body.analyzers,
        environment=body.environment,
    )

    await db.commit()

    return result.to_dict()


@router.get("/projects/{project_id}/scans/latest", status_code=200)
async def get_latest_scan(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the latest scan results for a project.

    Returns the most recent finding batch from pearl_scan sources.
    """
    from pearl.repositories.finding_repo import FindingRepository
    from sqlalchemy import select, desc
    from pearl.db.models.finding import FindingBatchRow, FindingRow

    await _ensure_project(project_id, db)

    # Find latest scan batch for this project
    stmt = (
        select(FindingBatchRow)
        .where(FindingBatchRow.source_system.like("pearl_scan%"))
        .order_by(desc(FindingBatchRow.created_at))
        .limit(1)
    )
    result = await db.execute(stmt)
    batch = result.scalar_one_or_none()

    if not batch:
        return {
            "project_id": project_id,
            "message": "No scans found for this project",
            "scans": [],
        }

    # Get findings from this batch
    findings_stmt = (
        select(FindingRow)
        .where(FindingRow.batch_id == batch.batch_id)
        .where(FindingRow.project_id == project_id)
    )
    findings_result = await db.execute(findings_stmt)
    findings = list(findings_result.scalars().all())

    severity_counts: dict[str, int] = {}
    for f in findings:
        severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

    return {
        "project_id": project_id,
        "batch_id": batch.batch_id,
        "source_system": batch.source_system,
        "scanned_at": batch.created_at.isoformat() if batch.created_at else None,
        "total_findings": len(findings),
        "findings_by_severity": severity_counts,
        "findings": [
            {
                "finding_id": f.finding_id,
                "title": f.title,
                "severity": f.severity,
                "category": f.category,
                "status": f.status,
                "compliance_refs": f.compliance_refs,
            }
            for f in findings
        ],
    }


@router.post("/projects/{project_id}/scans/security-review", status_code=202)
async def ingest_security_review(
    project_id: str,
    body: SecurityReviewIngestRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Parse /security-review markdown output and ingest as PeaRL findings."""
    from pearl.scanning.integrations.security_review import parse_security_review
    from pearl.repositories.finding_repo import FindingBatchRepository, FindingRepository
    from pearl.services.id_generator import generate_id

    await _ensure_project(project_id, db)

    # Parse the markdown
    ingest_data = parse_security_review(
        markdown=body.markdown,
        project_id=project_id,
        environment=body.environment,
    )

    batch_id = ingest_data["source_batch"]["batch_id"]
    accepted = 0
    quarantined = 0

    finding_repo = FindingRepository(db)
    for finding_data in ingest_data["findings"]:
        try:
            finding_id = generate_id("find_")
            await finding_repo.create(
                finding_id=finding_id,
                project_id=project_id,
                environment=body.environment,
                category=finding_data["category"],
                severity=finding_data["severity"],
                title=finding_data["title"],
                source=finding_data["source"],
                full_data=finding_data,
                normalized=False,
                detected_at=datetime.fromisoformat(finding_data["detected_at"]),
                batch_id=batch_id,
                cwe_ids=finding_data.get("cwe_ids"),
                compliance_refs=finding_data.get("compliance_refs"),
                status=finding_data.get("status", "open"),
            )
            accepted += 1
        except Exception:
            quarantined += 1

    # Create batch record
    batch_repo = FindingBatchRepository(db)
    await batch_repo.create(
        batch_id=batch_id,
        source_system="claude_security_review",
        trust_label="manual_unverified",
        accepted_count=accepted,
        quarantined_count=quarantined,
        normalized_count=0,
    )

    await db.commit()

    return {
        "batch_id": batch_id,
        "accepted_count": accepted,
        "quarantined_count": quarantined,
        "total_findings_parsed": len(ingest_data["findings"]),
        "trace_id": trace_id,
    }


@router.get("/scanning/analyzers", status_code=200)
async def list_analyzers() -> list[dict]:
    """List available scanning analyzers."""
    return _service.get_analyzer_info()
