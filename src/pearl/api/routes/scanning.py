"""Scanning API routes — trigger scans, get results, ingest security reviews."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
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


@router.post("/projects/{project_id}/scan-targets/{scan_target_id}/scan", status_code=202)
async def trigger_scan_target(
    project_id: str,
    scan_target_id: str,
    request=None,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Trigger an on-demand scan for a specific scan target."""
    from fastapi import Request
    from pearl.workers.queue import enqueue_job

    await _ensure_project(project_id, db)

    # Verify scan target exists
    from pearl.repositories.scan_target_repo import ScanTargetRepository
    target_repo = ScanTargetRepository(db)
    target = await target_repo.get(scan_target_id)
    if not target or target.project_id != project_id:
        from pearl.errors.exceptions import NotFoundError
        raise NotFoundError("ScanTarget", scan_target_id)

    # Enqueue scan job
    redis = None
    if request:
        redis = getattr(request.app.state, "redis", None)

    job = await enqueue_job(
        session=db,
        job_type="scan_source",
        project_id=project_id,
        trace_id=trace_id,
        payload={
            "project_id": project_id,
            "scan_target_id": scan_target_id,
            "environment": (target.environment_scope or ["dev"])[0],
        },
        redis=redis,
    )
    await db.commit()

    return {"job_id": job.job_id, "status": job.status, "scan_target_id": scan_target_id}


@router.get("/scanning/analyzers", status_code=200)
async def list_analyzers() -> list[dict]:
    """List available scanning analyzers."""
    return _service.get_analyzer_info()


# ---------------------------------------------------------------------------
# Snyk SCA ingest route
# ---------------------------------------------------------------------------

_SNYK_SEVERITY_MAP = {
    "critical": "critical",
    "high": "high",
    "medium": "moderate",
    "low": "low",
}


class SnykVuln(BaseModel):
    model_config = {"populate_by_name": True}

    id: str
    title: str | None = None
    severity: str = "low"
    packageName: str = ""
    version: str | None = None
    fixedIn: list[str] = []
    description: str | None = None
    identifiers: dict[str, Any] = {}
    references: list[dict[str, Any]] = []
    from_path: list[str] = Field(default=[], alias="from")


class SnykIngestRequest(BaseModel):
    vulnerabilities: list[SnykVuln] = []


@router.post("/projects/{project_id}/integrations/snyk/ingest", status_code=200)
async def snyk_ingest(
    project_id: str,
    body: SnykIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest raw `snyk test --json` output and upsert findings into PeaRL.

    Upserts by external_id (stored in source.external_id).
    Auto-resolves open snyk_sca findings not present in the current scan.
    """
    from pearl.db.models.finding import FindingRow
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.services.id_generator import generate_id

    await _ensure_project(project_id, db)

    # Load all existing snyk findings for this project (any status)
    stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["tool_name"].as_string() == "snyk_sca",
    )
    result = await db.execute(stmt)
    existing_findings: list[FindingRow] = list(result.scalars().all())
    existing_by_ext_id: dict[str, FindingRow] = {
        (f.source or {}).get("external_id", ""): f
        for f in existing_findings
    }

    finding_repo = FindingRepository(db)
    created = 0
    updated = 0
    current_ext_ids: set[str] = set()

    for vuln in body.vulnerabilities:
        ext_id = f"snyk-{vuln.id}-{vuln.packageName}"
        current_ext_ids.add(ext_id)
        severity = _SNYK_SEVERITY_MAP.get(vuln.severity.lower(), "low")
        title = vuln.title or f"Snyk: {vuln.packageName} - {vuln.id}"
        source = {
            "tool_name": "snyk_sca",
            "system": "snyk",
            "external_id": ext_id,
        }
        full_data = {
            "id": vuln.id,
            "title": vuln.title,
            "severity": vuln.severity,
            "packageName": vuln.packageName,
            "version": vuln.version,
            "fixedIn": vuln.fixedIn,
            "description": vuln.description,
            "identifiers": vuln.identifiers,
            "references": vuln.references,
            "from": vuln.from_path,
        }

        existing = existing_by_ext_id.get(ext_id)
        if existing:
            existing.full_data = full_data
            existing.title = title
            existing.severity = severity
            await db.flush()
            updated += 1
        else:
            await finding_repo.create(
                finding_id=generate_id("find_"),
                project_id=project_id,
                environment="dev",
                category="security",
                severity=severity,
                title=title,
                source=source,
                full_data=full_data,
                normalized=True,
                detected_at=datetime.now(timezone.utc),
                batch_id=None,
                status="open",
                schema_version="1.1",
            )
            created += 1

    # Auto-resolve open snyk_sca findings not in current scan
    resolved = 0
    for f in existing_findings:
        ext_id = (f.source or {}).get("external_id", "")
        if f.status == "open" and ext_id not in current_ext_ids:
            f.status = "resolved"
            f.resolved_at = datetime.now(timezone.utc)
            await db.flush()
            resolved += 1

    await db.commit()

    # Count open snyk findings by severity after ingest
    sev_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["tool_name"].as_string() == "snyk_sca",
        FindingRow.status == "open",
    )
    sev_result = await db.execute(sev_stmt)
    open_snyk = list(sev_result.scalars().all())
    sev_counts: dict[str, int] = {}
    for f in open_snyk:
        sev_counts[f.severity] = sev_counts.get(f.severity, 0) + 1

    return {
        "project_id": project_id,
        "findings_created": created,
        "findings_updated": updated,
        "findings_resolved": resolved,
        "critical": sev_counts.get("critical", 0),
        "high": sev_counts.get("high", 0),
        "medium": sev_counts.get("moderate", 0),
        "low": sev_counts.get("low", 0),
    }


# ---------------------------------------------------------------------------
# MASS 2.0 ingest route
# ---------------------------------------------------------------------------

_MASS_CATEGORY_MAP: dict[str, str] = {
    "prompt_injection": "security",
    "jailbreak": "security",
    "secret_leak": "security",
    "infra_misconfiguration": "security",
    "mcp_vulnerability": "security",
    "rag_vulnerability": "security",
    "model_file_risk": "security",
    "bias": "responsible_ai",
    "toxicity": "responsible_ai",
}


class MassFinding(BaseModel):
    finding_id: str
    category: str
    severity: str = "low"
    title: str
    description: str | None = None
    location: str | None = None
    remediation: str | None = None
    false_positive: bool = False


class MassIngestRequest(BaseModel):
    scan_id: str
    risk_score: float = 0.0
    categories_completed: list[str] = []
    findings: list[MassFinding] = []


@router.post("/projects/{project_id}/integrations/mass/ingest", status_code=200)
async def mass_ingest(
    project_id: str,
    body: MassIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest MASS 2.0 AI security scan results into PeaRL.

    Upserts by external_id (stored in source.external_id).
    Auto-resolves open mass2 findings not present in current scan.
    Creates/updates an informational marker finding used by gate rules.
    """
    from pearl.db.models.finding import FindingRow
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.services.id_generator import generate_id

    await _ensure_project(project_id, db)

    # Load all existing MASS findings for this project (any status)
    stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["tool_name"].as_string() == "mass2",
    )
    result = await db.execute(stmt)
    existing_mass: list[FindingRow] = list(result.scalars().all())
    existing_by_ext_id: dict[str, FindingRow] = {
        (f.source or {}).get("external_id", ""): f
        for f in existing_mass
    }

    finding_repo = FindingRepository(db)
    created = 0
    updated = 0
    current_ext_ids: set[str] = set()

    for mf in body.findings:
        ext_id = f"mass-{body.scan_id}-{mf.finding_id}"
        current_ext_ids.add(ext_id)
        status = "closed" if mf.false_positive else "open"
        # "info" maps to "low"
        severity = "low" if mf.severity == "info" else mf.severity
        category = _MASS_CATEGORY_MAP.get(mf.category, "security")
        source = {
            "tool_name": "mass2",
            "system": "mass_scan",
            "trust_label": "trusted_external",
            "scan_id": body.scan_id,
            "external_id": ext_id,
        }
        full_data = {
            "finding_id": mf.finding_id,
            "category": mf.category,
            "severity": mf.severity,
            "title": mf.title,
            "description": mf.description,
            "location": mf.location,
            "remediation": mf.remediation,
            "false_positive": mf.false_positive,
        }

        existing = existing_by_ext_id.get(ext_id)
        if existing:
            existing.full_data = full_data
            existing.status = status
            existing.severity = severity
            await db.flush()
            updated += 1
        else:
            await finding_repo.create(
                finding_id=generate_id("find_"),
                project_id=project_id,
                environment="dev",
                category=category,
                severity=severity,
                title=mf.title,
                source=source,
                full_data=full_data,
                normalized=True,
                detected_at=datetime.now(timezone.utc),
                batch_id=None,
                status=status,
                schema_version="1.1",
            )
            created += 1

    # Auto-resolve open mass2 findings not in current scan
    resolved = 0
    for f in existing_mass:
        ext_id = (f.source or {}).get("external_id", "")
        if f.status == "open" and ext_id not in current_ext_ids:
            f.status = "resolved"
            f.resolved_at = datetime.now(timezone.utc)
            await db.flush()
            resolved += 1

    # Upsert MASS marker finding (drives AI_SCAN_COMPLETED and AI_RISK_ACCEPTABLE)
    marker_ext_id = f"mass-marker-{project_id}"
    marker_source = {
        "tool_name": "mass2_marker",
        "system": "mass_scan",
        "scan_id": body.scan_id,
        "external_id": marker_ext_id,
    }
    marker_full_data = {
        "risk_score": body.risk_score,
        "categories_completed": body.categories_completed,
        "scan_id": body.scan_id,
    }

    marker_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["external_id"].as_string() == marker_ext_id,
    ).limit(1)
    marker_result = await db.execute(marker_stmt)
    marker_row = marker_result.scalar_one_or_none()

    if marker_row:
        marker_row.source = marker_source
        marker_row.full_data = marker_full_data
        await db.flush()
    else:
        await finding_repo.create(
            finding_id=generate_id("find_"),
            project_id=project_id,
            environment="dev",
            category="security",
            severity="low",
            title="MASS 2.0 AI Security Scan Completed",
            source=marker_source,
            full_data=marker_full_data,
            normalized=True,
            detected_at=datetime.now(timezone.utc),
            batch_id=None,
            status="open",
            schema_version="1.1",
        )

    await db.commit()

    return {
        "project_id": project_id,
        "scan_id": body.scan_id,
        "findings_created": created,
        "findings_updated": updated,
        "findings_resolved": resolved,
        "categories_completed": body.categories_completed,
        "risk_score": body.risk_score,
    }


# ---------------------------------------------------------------------------
# SonarQube integration routes
# ---------------------------------------------------------------------------


class SonarScanRequest(BaseModel):
    target_path: str


async def _get_sonarqube_endpoint(project_id: str, db: AsyncSession):
    """Load the SonarQube IntegrationEndpoint for a project (with org-level fallback)."""
    from pearl.integrations.config import AuthConfig, IntegrationEndpoint
    from pearl.models.enums import IntegrationCategory, IntegrationType
    from pearl.repositories.integration_repo import IntegrationEndpointRepository

    integration_repo = IntegrationEndpointRepository(db)

    # Try project-level first
    endpoints = await integration_repo.list_by_project(project_id)
    row = next((e for e in endpoints if e.adapter_type == "sonarqube"), None)

    # Fall back to org-level
    if row is None:
        row = await integration_repo.get_org_by_adapter_type("sonarqube")

    if row is None:
        raise NotFoundError("SonarQube integration", f"project={project_id}")

    auth_data = row.auth_config or {}
    endpoint = IntegrationEndpoint(
        endpoint_id=row.endpoint_id,
        name=row.name,
        adapter_type=row.adapter_type,
        integration_type=IntegrationType(row.integration_type),
        category=IntegrationCategory(row.category),
        base_url=row.base_url,
        auth=AuthConfig(**auth_data) if auth_data else AuthConfig(),
        project_mapping=row.project_mapping,
        enabled=row.enabled,
        labels=row.labels,
    )
    return endpoint, row


@router.post("/projects/{project_id}/integrations/sonarqube/pull", status_code=200)
async def sonarqube_pull(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Pull findings from SonarQube and ingest into PeaRL.

    Upserts findings by external_id+source_tool — updates existing, creates new.
    Also fetches quality gate status.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from pearl.db.models.finding import FindingRow
    from pearl.integrations.adapters.sonarqube import SonarQubeAdapter
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.services.id_generator import generate_id

    await _ensure_project(project_id, db)
    endpoint, endpoint_row = await _get_sonarqube_endpoint(project_id, db)

    adapter = SonarQubeAdapter()
    findings = await adapter.pull_findings(endpoint, since=None)

    finding_repo = FindingRepository(db)
    new_count = 0
    updated_count = 0

    for nf in findings:
        # Check for existing finding by external_id in source JSON
        stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
        ).where(
            FindingRow.source["raw_record_ref"].as_string() == nf.external_id,
        ).where(
            FindingRow.source["tool_name"].as_string() == "sonarqube",
        ).limit(1)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing finding
            existing.title = nf.title
            existing.severity = nf.severity
            existing.category = nf.category
            existing.full_data = nf.raw_record or {}
            existing.cwe_ids = nf.cwe_ids
            existing.status = existing.status  # preserve current status
            await db.flush()
            updated_count += 1
        else:
            # Create new finding
            finding_id = generate_id("find_")
            await finding_repo.create(
                finding_id=finding_id,
                project_id=project_id,
                environment="dev",
                category=nf.category,
                severity=nf.severity,
                title=nf.title,
                source={
                    "tool_name": "sonarqube",
                    "tool_type": nf.source_type,
                    "trust_label": "trusted_external_registered",
                    "raw_record_ref": nf.external_id,
                },
                full_data=nf.raw_record or {},
                normalized=False,
                detected_at=nf.detected_at,
                batch_id=None,
                cwe_ids=nf.cwe_ids,
                compliance_refs=None,
                status="open",
            )
            new_count += 1

    # Fetch quality gate
    labels = endpoint.labels or {}
    project_key = labels.get("project_key", project_id)
    qg = await adapter.get_quality_gate_status(endpoint, project_key)

    # Update last_sync on endpoint
    endpoint_row.last_sync_at = datetime.now(timezone.utc)
    endpoint_row.last_sync_status = "success"
    await db.flush()
    await db.commit()

    last_pull_at = datetime.now(timezone.utc).isoformat()
    return {
        "pulled": len(findings),
        "new": new_count,
        "updated": updated_count,
        "quality_gate": qg.get("status", "UNKNOWN"),
        "last_pull_at": last_pull_at,
    }


@router.get("/projects/{project_id}/integrations/sonarqube/status", status_code=200)
async def sonarqube_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get SonarQube integration status for a project.

    Returns quality gate status and findings breakdown by severity.
    """
    from sqlalchemy import func, select

    from pearl.db.models.finding import FindingRow
    from pearl.integrations.adapters.sonarqube import SonarQubeAdapter

    await _ensure_project(project_id, db)

    try:
        endpoint, endpoint_row = await _get_sonarqube_endpoint(project_id, db)
    except NotFoundError:
        # Return a structured response even when no integration is configured
        return {
            "quality_gate": None,
            "findings_by_severity": {},
            "last_pull_at": None,
            "integration_configured": False,
        }

    adapter = SonarQubeAdapter()
    labels = endpoint.labels or {}
    project_key = labels.get("project_key", project_id)
    qg = await adapter.get_quality_gate_status(endpoint, project_key)

    # Count sonarqube findings by severity
    stmt = (
        select(FindingRow.severity, func.count(FindingRow.finding_id))
        .where(FindingRow.project_id == project_id)
        .where(FindingRow.source["tool_name"].as_string() == "sonarqube")
        .where(FindingRow.status != "closed")
        .group_by(FindingRow.severity)
    )
    result = await db.execute(stmt)
    findings_by_severity = dict(result.all())

    last_pull_at = (
        endpoint_row.last_sync_at.isoformat()
        if endpoint_row.last_sync_at
        else None
    )

    return {
        "quality_gate": qg.get("status", "UNKNOWN"),
        "findings_by_severity": findings_by_severity,
        "last_pull_at": last_pull_at,
        "integration_configured": True,
    }


@router.post("/projects/{project_id}/integrations/sonarqube/scan", status_code=202)
async def sonarqube_scan(
    project_id: str,
    body: SonarScanRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Enqueue a SonarQube scan job for a registered target path.

    The target_path must be registered as a ScanTarget for this project to
    prevent arbitrary path scanning.
    """
    from pearl.repositories.scan_target_repo import ScanTargetRepository
    from pearl.workers.queue import enqueue_job

    await _ensure_project(project_id, db)

    # Validate path — no traversal
    resolved = Path(body.target_path).resolve()
    if ".." in body.target_path:
        raise ValidationError("target_path must not contain path traversal sequences")

    # Verify target_path is registered for this project
    target_repo = ScanTargetRepository(db)
    all_targets = await target_repo.list_by_project(project_id)
    matched = next(
        (t for t in all_targets if Path(t.repo_url).resolve() == resolved or t.repo_url == str(resolved)),
        None,
    )
    if matched is None:
        raise ValidationError(
            f"target_path '{body.target_path}' is not registered as a scan target for this project"
        )

    redis = getattr(request.app.state, "redis", None)

    job = await enqueue_job(
        session=db,
        job_type="sonar_scan",
        project_id=project_id,
        trace_id=trace_id,
        payload={"target_path": str(resolved), "project_id": project_id},
        redis=redis,
    )
    await db.commit()

    return {
        "job_id": job.job_id,
        "status": "queued",
        "message": "Scan enqueued. Poll getJobStatus for completion.",
    }
