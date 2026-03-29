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
    """Pull SonarQube quality gate status and ingest into PeaRL.

    PeaRL is the gate-checker, not a finding mirror. This route:
    1. Fetches quality gate status + key metrics → stored as ONE summary finding
    2. Ingests individual issues ONLY for BLOCKER severity (→ critical PeaRL findings)
    3. Provides a link to SonarQube for full issue detail

    The quality gate summary finding drives the SONARQUBE_QUALITY_GATE gate rule.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from pearl.db.models.finding import FindingRow
    from pearl.integrations.adapters.sonarqube import SonarQubeAdapter
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.services.id_generator import generate_id

    await _ensure_project(project_id, db)
    endpoint, endpoint_row = await _get_sonarqube_endpoint(project_id, db)

    from pearl.config import settings as _pearl_settings
    adapter = SonarQubeAdapter()
    labels = endpoint.labels or {}
    project_key = labels.get("project_key", project_id)
    base_url = endpoint.base_url.rstrip("/")
    # Use public URL for browser-accessible links (falls back to base_url)
    _settings = _pearl_settings
    public_base = (_settings.sonar_url or base_url).rstrip("/")
    sonarqube_link = f"{public_base}/dashboard?id={project_key}"

    # 1. Fetch quality gate status and metrics in parallel
    qg = await adapter.get_quality_gate_status(endpoint, project_key)
    metrics = await adapter.get_metrics(endpoint, project_key)

    qg_status = qg.get("status", "UNKNOWN")  # OK | WARN | ERROR | UNKNOWN
    qg_conditions = qg.get("conditions", [])

    # 2. Upsert the quality gate summary finding (one per project)
    finding_repo = FindingRepository(db)
    summary_severity = {"OK": "low", "WARN": "moderate", "ERROR": "high"}.get(qg_status, "moderate")
    summary_title = f"SonarQube Quality Gate: {qg_status} — {project_key}"
    summary_full_data = {
        "quality_gate_status": qg_status,
        "conditions": qg_conditions,
        "metrics": metrics,
        "sonarqube_link": sonarqube_link,
        "project_key": project_key,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
        "source": {"tool_name": "sonarqube_quality_gate", "tool_type": "sast", "trust_label": "trusted_external_registered"},
    }

    # Find existing summary finding for this project
    stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["tool_name"].as_string() == "sonarqube_quality_gate",
    ).limit(1)
    result = await db.execute(stmt)
    existing_summary = result.scalar_one_or_none()

    if existing_summary:
        existing_summary.title = summary_title
        existing_summary.severity = summary_severity
        existing_summary.full_data = summary_full_data
        existing_summary.status = "open" if qg_status != "OK" else "resolved"
        await db.flush()
    else:
        summary_id = generate_id("find_")
        await finding_repo.create(
            finding_id=summary_id,
            project_id=project_id,
            environment="dev",
            category="governance",
            severity=summary_severity,
            title=summary_title,
            source={"tool_name": "sonarqube_quality_gate", "tool_type": "sast", "trust_label": "trusted_external_registered"},
            full_data=summary_full_data,
            normalized=False,
            detected_at=datetime.now(timezone.utc),
            batch_id=None,
            cwe_ids=None,
            compliance_refs=None,
            status="open" if qg_status != "OK" else "resolved",
        )

    # 3. Ingest BLOCKER and HIGH issues as individual PeaRL findings
    all_findings = await adapter.pull_findings(endpoint, since=None)
    severity_map = {"BLOCKER": "critical", "HIGH": "high"}
    ingested_findings = [
        nf for nf in all_findings
        if (nf.raw_record or {}).get("severity") in severity_map
    ]

    new_count = 0
    updated_count = 0

    for nf in ingested_findings:
        sonar_severity = (nf.raw_record or {}).get("severity", "HIGH")
        pearl_severity = severity_map.get(sonar_severity, "high")
        stmt2 = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.source["raw_record_ref"].as_string() == nf.external_id,
            FindingRow.source["tool_name"].as_string() == "sonarqube",
        ).limit(1)
        existing_row = (await db.execute(stmt2)).scalar_one_or_none()

        if existing_row:
            existing_row.title = nf.title
            existing_row.severity = pearl_severity
            existing_row.full_data = {**(nf.raw_record or {}), "sonarqube_link": sonarqube_link}
            await db.flush()
            updated_count += 1
        else:
            finding_id = generate_id("find_")
            await finding_repo.create(
                finding_id=finding_id,
                project_id=project_id,
                environment="dev",
                category=nf.category,
                severity=pearl_severity,
                title=f"[SonarQube {sonar_severity}] {nf.title}",
                source={
                    "tool_name": "sonarqube",
                    "tool_type": nf.source_type,
                    "trust_label": "trusted_external_registered",
                    "raw_record_ref": nf.external_id,
                    "sonarqube_link": sonarqube_link,
                },
                full_data={**(nf.raw_record or {}), "sonarqube_link": sonarqube_link},
                normalized=False,
                detected_at=nf.detected_at,
                batch_id=None,
                cwe_ids=nf.cwe_ids,
                compliance_refs=None,
                status="open",
            )
            new_count += 1

    # Update last_sync on endpoint
    endpoint_row.last_sync_at = datetime.now(timezone.utc)
    endpoint_row.last_sync_status = "success"
    await db.flush()
    await db.commit()

    return {
        "quality_gate": qg_status,
        "sonarqube_link": sonarqube_link,
        "metrics": metrics,
        "blockers_ingested": new_count + updated_count,
        "blockers_new": new_count,
        "blockers_updated": updated_count,
        "last_pull_at": datetime.now(timezone.utc).isoformat(),
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

    await _ensure_project(project_id, db)

    try:
        endpoint, endpoint_row = await _get_sonarqube_endpoint(project_id, db)
    except NotFoundError:
        # Return a structured response even when no integration is configured
        return {
            "quality_gate": None,
            "metrics": {},
            "open_blockers_in_pearl": 0,
            "last_pull_at": None,
            "integration_configured": False,
        }

    # Load last quality gate summary finding from DB (populated by pull)
    summary_stmt = (
        select(FindingRow)
        .where(FindingRow.project_id == project_id)
        .where(FindingRow.source["tool_name"].as_string() == "sonarqube_quality_gate")
        .limit(1)
    )
    summary_result = await db.execute(summary_stmt)
    summary_finding = summary_result.scalar_one_or_none()

    # Count BLOCKER findings ingested into PeaRL
    blocker_stmt = (
        select(func.count(FindingRow.finding_id))
        .where(FindingRow.project_id == project_id)
        .where(FindingRow.source["tool_name"].as_string() == "sonarqube")
        .where(FindingRow.status == "open")
    )
    blocker_count = (await db.execute(blocker_stmt)).scalar_one_or_none() or 0

    last_pull_at = (
        endpoint_row.last_sync_at.isoformat()
        if endpoint_row.last_sync_at
        else None
    )

    from pearl.config import settings as _pearl_settings
    qg_data = (summary_finding.full_data or {}) if summary_finding else {}
    labels = endpoint.labels or {}
    project_key = labels.get("project_key", project_id)
    _settings = _pearl_settings
    public_base = (_settings.sonar_url or endpoint.base_url).rstrip("/")
    sonarqube_link = f"{public_base}/dashboard?id={project_key}"
    issues_link = f"{public_base}/project/issues?impactSeverities=HIGH,BLOCKER&issueStatuses=CONFIRMED,OPEN&id={project_key}"

    return {
        "quality_gate": qg_data.get("quality_gate_status", "UNKNOWN"),
        "metrics": qg_data.get("metrics", {}),
        "conditions": qg_data.get("conditions", []),
        "sonarqube_link": sonarqube_link,
        "sonarqube_issues_link": issues_link,
        "open_findings_in_pearl": blocker_count,
        "last_pull_at": last_pull_at,
        "integration_configured": True,
    }


# ---------------------------------------------------------------------------
# Snyk CLI ingest route
# ---------------------------------------------------------------------------


class SnykIngestRequest(BaseModel):
    """Raw `snyk test --json` output."""
    vulnerabilities: list[dict] = []
    ok: bool = False
    dependency_count: int = Field(0, alias="dependencyCount")
    package_manager: str = Field("", alias="packageManager")
    project_name: str = Field("", alias="projectName")

    model_config = {"populate_by_name": True}


@router.post("/projects/{project_id}/integrations/snyk/ingest", status_code=200)
async def snyk_ingest(
    project_id: str,
    body: SnykIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest Snyk CLI JSON output (`snyk test --json`) into PeaRL findings.

    Creates or updates findings for each vulnerability.  Previously-open Snyk
    findings that are absent from this scan are automatically resolved.
    """
    from sqlalchemy import select

    from pearl.db.models.finding import FindingRow
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.services.id_generator import generate_id

    await _ensure_project(project_id, db)

    _SEV_MAP = {
        "critical": "critical",
        "high": "high",
        "medium": "moderate",
        "low": "low",
    }

    finding_repo = FindingRepository(db)
    created = 0
    updated = 0
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    processed_external_ids: list[str] = []

    for vuln in body.vulnerabilities:
        external_id = f"snyk-{vuln.get('id', '')}-{vuln.get('pkgName', '')}"
        processed_external_ids.append(external_id)

        pearl_severity = _SEV_MAP.get(vuln.get("severity", "low"), "low")
        sev_key = vuln.get("severity", "low")
        if sev_key in severity_counts:
            severity_counts[sev_key] += 1

        source = {"system": "snyk", "tool": "snyk_cli", "trust_label": "ci_trusted"}
        full_data = {
            **vuln,
            "source": source,
            "tool_name": "snyk_sca",
        }
        title = vuln.get("title", vuln.get("id", external_id))

        stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.source["system"].as_string() == "snyk",
            FindingRow.full_data["tool_name"].as_string() == "snyk_sca",
        ).where(
            FindingRow.full_data["id"].as_string() == str(vuln.get("id", "")),
        ).limit(1)
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.title = title
            existing.severity = pearl_severity
            existing.full_data = full_data
            existing.source = source
            existing.status = "open"
            await db.flush()
            updated += 1
        else:
            finding_id = generate_id("find_")
            await finding_repo.create(
                finding_id=finding_id,
                project_id=project_id,
                environment="dev",
                category="security",
                severity=pearl_severity,
                title=title,
                source=source,
                full_data=full_data,
                normalized=False,
                detected_at=datetime.now(timezone.utc),
                batch_id=None,
                cwe_ids=vuln.get("identifiers", {}).get("CWE") or None,
                compliance_refs=None,
                status="open",
            )
            created += 1

    # Auto-resolve previously-open Snyk findings not in this scan
    if processed_external_ids:
        # Fetch all open snyk findings to resolve the ones not in this scan
        resolve_stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.source["system"].as_string() == "snyk",
            FindingRow.status == "open",
        )
        resolve_result = await db.execute(resolve_stmt)
        for stale in resolve_result.scalars().all():
            # Build external_id from stored full_data
            stored_id = (stale.full_data or {}).get("id", "")
            stored_pkg = (stale.full_data or {}).get("pkgName", "")
            stale_ext_id = f"snyk-{stored_id}-{stored_pkg}"
            if stale_ext_id not in processed_external_ids:
                stale.status = "resolved"
                await db.flush()
    elif body.vulnerabilities == []:
        # Empty scan — resolve all open Snyk findings
        resolve_stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.source["system"].as_string() == "snyk",
            FindingRow.status == "open",
        )
        resolve_result = await db.execute(resolve_stmt)
        for stale in resolve_result.scalars().all():
            stale.status = "resolved"
            await db.flush()

    # Upsert a scan-completed marker so the gate evaluator knows a scan ran
    # even when 0 vulnerabilities are found.
    marker_ext_id = f"snyk-scan-marker-{project_id}"
    marker_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.full_data["external_id"].as_string() == marker_ext_id,
    ).limit(1)
    marker_row = (await db.execute(marker_stmt)).scalar_one_or_none()
    total_high_critical = severity_counts.get("critical", 0) + severity_counts.get("high", 0)
    marker_source = {"system": "snyk", "tool": "snyk_cli", "trust_label": "ci_trusted"}
    if marker_row:
        marker_row.title = f"Snyk SCA scan completed — {project_id}"
        marker_row.full_data = {
            "external_id": marker_ext_id,
            "scan_marker": True,
            "high_critical_count": total_high_critical,
            "dependency_count": body.dependency_count,
        }
        marker_row.source = marker_source
        marker_row.status = "open"
        await db.flush()
    else:
        await finding_repo.create(
            finding_id=generate_id("find_"),
            project_id=project_id,
            environment="dev",
            category="governance",
            severity="low",
            title=f"Snyk SCA scan completed — {project_id}",
            source=marker_source,
            full_data={
                "external_id": marker_ext_id,
                "scan_marker": True,
                "high_critical_count": total_high_critical,
                "dependency_count": body.dependency_count,
            },
            normalized=False,
            detected_at=datetime.now(timezone.utc),
            batch_id=None,
            status="open",
        )

    await db.commit()

    return {
        "project_id": project_id,
        "findings_created": created,
        "findings_updated": updated,
        "critical": severity_counts.get("critical", 0),
        "high": severity_counts.get("high", 0),
        "medium": severity_counts.get("medium", 0),
        "low": severity_counts.get("low", 0),
    }


# ---------------------------------------------------------------------------
# MASS ingest route
# ---------------------------------------------------------------------------


_MASS_CATEGORY_MAP = {
    # security categories
    "prompt_injection": "security",
    "jailbreak": "security",
    "secret_leak": "security",
    "infra_misconfiguration": "security",
    "mcp_vulnerability": "security",
    "rag_vulnerability": "security",
    "model_file_risk": "security",
    # responsible_ai categories
    "bias": "responsible_ai",
    "toxicity": "responsible_ai",
}


class MassIngestRequest(BaseModel):
    scan_id: str
    findings: list[dict] = []
    risk_score: float = 0.0
    categories_completed: list[str] = []


@router.post("/projects/{project_id}/integrations/mass/ingest", status_code=200)
async def mass_ingest(
    project_id: str,
    body: MassIngestRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Ingest MASS 2.0 scan results into PeaRL findings.

    Creates or updates findings for each MASS finding.  Previously-open MASS
    findings absent from this scan are automatically resolved.  A marker
    finding (mass_scan_completed) is written at the end for gate evaluation.
    """
    from sqlalchemy import select

    from pearl.db.models.finding import FindingRow
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.services.id_generator import generate_id

    await _ensure_project(project_id, db)

    finding_repo = FindingRepository(db)
    created = 0
    processed_external_ids: list[str] = []

    source_base = {"system": "mass_scan", "tool": "mass2", "trust_label": "trusted_external"}

    for finding in body.findings:
        external_id = f"mass-{finding.get('finding_id', '')}"
        processed_external_ids.append(external_id)

        status = "closed" if finding.get("false_positive", False) else "open"
        pearl_category = _MASS_CATEGORY_MAP.get(finding.get("category", ""), "security")
        severity = finding.get("severity", "moderate")

        full_data = {**finding, "source": source_base}

        stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.source["system"].as_string() == "mass_scan",
            FindingRow.full_data["finding_id"].as_string() == str(finding.get("finding_id", "")),
        ).limit(1)
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.title = finding.get("title", external_id)
            existing.severity = severity
            existing.full_data = full_data
            existing.source = source_base
            existing.status = status
            await db.flush()
        else:
            finding_id = generate_id("find_")
            await finding_repo.create(
                finding_id=finding_id,
                project_id=project_id,
                environment="dev",
                category=pearl_category,
                severity=severity,
                title=finding.get("title", external_id),
                source=source_base,
                full_data=full_data,
                normalized=False,
                detected_at=datetime.now(timezone.utc),
                batch_id=None,
                cwe_ids=finding.get("cwe_ids") or None,
                compliance_refs=None,
                status=status,
            )
            created += 1

    # Auto-resolve previously-open MASS findings not in this scan
    resolve_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["system"].as_string() == "mass_scan",
        FindingRow.status == "open",
    )
    resolve_result = await db.execute(resolve_stmt)
    for stale in resolve_result.scalars().all():
        stale_ext_id = f"mass-{(stale.full_data or {}).get('finding_id', '')}"
        if stale_ext_id not in processed_external_ids:
            stale.status = "resolved"
            await db.flush()

    # Write marker finding (mass_scan_completed) for gate evaluation
    marker_source = {"system": "mass_scan", "tool": "mass2", "tool_name": "mass_scan_completed", "trust_label": "trusted_external"}
    marker_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["tool_name"].as_string() == "mass_scan_completed",
    ).limit(1)
    existing_marker = (await db.execute(marker_stmt)).scalar_one_or_none()

    marker_full_data = {
        "scan_id": body.scan_id,
        "risk_score": body.risk_score,
        "categories_completed": body.categories_completed,
        "source": marker_source,
    }

    if existing_marker:
        existing_marker.full_data = marker_full_data
        existing_marker.source = marker_source
        await db.flush()
    else:
        marker_id = generate_id("find_")
        await finding_repo.create(
            finding_id=marker_id,
            project_id=project_id,
            environment="dev",
            category="governance",
            severity="info",
            title="MASS scan completed",
            source=marker_source,
            full_data=marker_full_data,
            normalized=False,
            detected_at=datetime.now(timezone.utc),
            batch_id=None,
            cwe_ids=None,
            compliance_refs=None,
            status="resolved",
        )

    await db.commit()

    return {
        "project_id": project_id,
        "scan_id": body.scan_id,
        "findings_created": created,
        "categories_completed": body.categories_completed,
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
