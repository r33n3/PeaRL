"""Report generation API route."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.models.report import ReportRequest, ReportResponse
from pearl.repositories.approval_repo import ApprovalRequestRepository
from pearl.repositories.report_repo import ReportRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Reports"])


@router.get("/projects/{project_id}/reports")
async def list_reports(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List previously generated reports for a project."""
    repo = ReportRepository(db)
    reports = await repo.list_by_project(project_id)
    return [
        {
            "report_id": r.report_id,
            "report_type": r.report_type,
            "status": r.status,
            "format": r.format,
            "generated_at": r.generated_at.isoformat() if r.generated_at else None,
        }
        for r in reports
    ]


@router.get("/projects/{project_id}/reports/{report_id}")
async def get_report(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single report with its content."""
    repo = ReportRepository(db)
    r = await repo.get(report_id)
    if not r or r.project_id != project_id:
        from pearl.errors.exceptions import NotFoundError
        raise NotFoundError("Report", report_id)
    return {
        "report_id": r.report_id,
        "report_type": r.report_type,
        "status": r.status,
        "format": r.format,
        "content": r.content,
        "artifact_ref": r.artifact_ref,
        "generated_at": r.generated_at.isoformat() if r.generated_at else None,
    }


@router.post("/projects/{project_id}/reports/generate")
async def generate_report(
    project_id: str,
    request: ReportRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    report_id = generate_id("rpt_")

    # Generate report content based on type
    content = None
    if request.report_type == "release_readiness":
        content = await _generate_release_readiness(project_id, request, db)
    elif request.report_type == "gate_fulfillment":
        content = await _generate_gate_fulfillment(project_id, request, db)
    elif request.report_type == "elevation_audit":
        content = await _generate_elevation_audit(project_id, request, db)
    elif request.report_type == "findings_remediation":
        content = await _generate_findings_remediation(project_id, request, db)
    else:
        content = {"summary": {"project_id": project_id, "report_type": request.report_type}}

    response = ReportResponse(
        schema_version="1.1",
        report_id=report_id,
        report_type=request.report_type,
        status="ready",
        format=request.format,
        content=content,
        artifact_ref=None,
        trace_id=trace_id,
        generated_at=datetime.now(timezone.utc),
    )

    # Store report
    repo = ReportRepository(db)
    await repo.create(
        report_id=report_id,
        project_id=project_id,
        report_type=request.report_type,
        status="ready",
        format=request.format,
        content=content,
        trace_id=trace_id,
        generated_at=response.generated_at,
    )
    await db.commit()

    return response.model_dump(mode="json", exclude_none=True)


@router.post("/projects/{project_id}/reports/{report_id}/export")
async def export_report_pdf(
    project_id: str,
    report_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Generate PDF of a report and upload to MinIO. Returns download URL."""
    from pearl.errors.exceptions import NotFoundError

    repo = ReportRepository(db)
    r = await repo.get(report_id)
    if not r or r.project_id != project_id:
        raise NotFoundError("Report", report_id)

    # Render PDF
    from pearl.services.reports.pdf_renderer import render_report_pdf

    report_data = {
        "project_id": project_id,
        "report_type": r.report_type,
        "content": r.content or {},
        "generated_at": r.generated_at.isoformat() if r.generated_at else datetime.now(timezone.utc).isoformat(),
        "detail_level": (r.content or {}).get("detail_level", "compliance"),
    }
    pdf_bytes = render_report_pdf(report_data)

    # Upload PDF to MinIO
    pdf_url = await _upload_pdf_artifact(report_id, project_id, r.report_type, pdf_bytes)

    expires_at = None
    if pdf_url:
        from pearl.config import settings
        from datetime import timedelta

        expires_at = (datetime.now(timezone.utc) + timedelta(days=settings.report_url_ttl_days)).isoformat()

        # Update artifact_ref on the report row
        await repo.update(r, artifact_ref=pdf_url)
        await db.commit()

    return {
        "pdf_url": pdf_url,
        "expires_at": expires_at,
    }


# ---------------------------------------------------------------------------
# Private generator helpers
# ---------------------------------------------------------------------------


async def _generate_gate_fulfillment(
    project_id: str, request: ReportRequest, db: AsyncSession
) -> dict:
    from pearl.services.reports.gate_fulfillment import generate_gate_fulfillment

    content = await generate_gate_fulfillment(project_id, request, db)

    if request.format == "markdown":
        content["markdown"] = _render_gate_fulfillment_md(content)

    return content


async def _generate_elevation_audit(
    project_id: str, request: ReportRequest, db: AsyncSession
) -> dict:
    from pearl.services.reports.elevation_audit import generate_elevation_audit

    content = await generate_elevation_audit(project_id, request, db)

    if request.format == "markdown":
        content["markdown"] = _render_elevation_audit_md(content)

    return content


async def _generate_findings_remediation(
    project_id: str, request: ReportRequest, db: AsyncSession
) -> dict:
    from pearl.services.reports.findings_remediation import generate_findings_remediation

    content = await generate_findings_remediation(project_id, request, db)

    if request.format == "markdown":
        content["markdown"] = _render_findings_remediation_md(content)

    return content


async def _generate_release_readiness(
    project_id: str, request: ReportRequest, db: AsyncSession
) -> dict:
    """Generate a release readiness report with findings, promotion, and fairness status."""
    env = request.filters.get("environment", "prod") if request.filters else "prod"

    # Check for open approval requests (these are the hard blockers)
    approval_repo = ApprovalRequestRepository(db)
    pending = await approval_repo.list_by_field("project_id", project_id)
    blockers = []
    for appr in pending:
        if appr.status == "pending":
            blockers.append(f"Open approval request: {appr.approval_request_id}")

    ready = len(blockers) == 0

    result: dict = {
        "summary": {
            "project_id": project_id,
            "environment": env,
            "ready": ready,
        },
        "blockers": blockers,
    }

    # Supplementary: findings counts by severity
    risk_factors: list[str] = []
    findings_by_severity: dict[str, int] = {}
    try:
        from pearl.repositories.finding_repo import FindingRepository

        finding_repo = FindingRepository(db)
        all_findings = await finding_repo.list_by_field("project_id", project_id)
        for f in all_findings:
            sev = f.severity or "unknown"
            findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1

        if findings_by_severity:
            result["findings_by_severity"] = findings_by_severity
            critical = findings_by_severity.get("critical", 0)
            high = findings_by_severity.get("high", 0)
            if critical > 0:
                risk_factors.append(f"{critical} critical-severity finding(s)")
            if high > 0:
                risk_factors.append(f"{high} high-severity finding(s)")
    except Exception:
        findings_by_severity = {}

    # Supplementary: promotion readiness
    promotion = None
    try:
        from pearl.repositories.promotion_repo import PromotionEvaluationRepository

        eval_repo = PromotionEvaluationRepository(db)
        latest = await eval_repo.get_latest_by_project(project_id)
        if latest:
            promotion = {
                "source_environment": latest.source_environment,
                "target_environment": latest.target_environment,
                "status": latest.status,
                "passed_count": latest.passed_count,
                "total_count": latest.total_count,
                "progress_pct": latest.progress_pct,
                "blockers": latest.blockers,
            }
            result["promotion_readiness"] = promotion
            if latest.status != "passed":
                risk_factors.append(f"Promotion gate: {latest.status} ({latest.progress_pct}% passing)")
    except Exception:
        pass

    # Supplementary: fairness status (for AI-enabled projects)
    fairness = None
    try:
        from pearl.repositories.fairness_repo import FairnessCaseRepository, EvidencePackageRepository
        from pearl.repositories.project_repo import ProjectRepository

        proj_repo = ProjectRepository(db)
        project = await proj_repo.get(project_id)
        if project and project.ai_enabled:
            fc_repo = FairnessCaseRepository(db)
            fc = await fc_repo.get_by_project(project_id)
            if not fc:
                risk_factors.append("Fairness case not defined (AI-enabled project)")
            else:
                fairness = {"fairness_case": {"fc_id": fc.fc_id, "risk_tier": fc.risk_tier}}
            ev_repo = EvidencePackageRepository(db)
            ev_list = await ev_repo.list_by_project(project_id)
            if ev_list:
                latest_ev = ev_list[0]
                if fairness is None:
                    fairness = {}
                fairness["evidence"] = {
                    "evidence_id": latest_ev.evidence_id,
                    "attestation_status": latest_ev.attestation_status,
                }
            if fairness:
                result["fairness"] = fairness
    except Exception:
        pass

    if risk_factors:
        result["risk_factors"] = risk_factors

    # Render markdown if requested
    if request.format == "markdown":
        from pearl.services.markdown_renderer import render_release_readiness

        all_blockers = blockers + risk_factors
        result["markdown"] = render_release_readiness(
            project_id=project_id,
            environment=env,
            findings_by_severity=findings_by_severity,
            approval_blockers=all_blockers,
            promotion=promotion,
            fairness=fairness,
        )

    return result


# ---------------------------------------------------------------------------
# Private markdown render helpers
# ---------------------------------------------------------------------------


def _render_gate_fulfillment_md(content: dict) -> str:
    lines: list[str] = []
    project_id = content.get("project_id", "?")
    env = content.get("environment_target", "?")
    lines.append(f"# Gate Fulfillment Report: {project_id}")
    lines.append("")
    lines.append(f"**Environment Target:** {env}")
    lines.append(f"**Generated At:** {content.get('generated_at', '')}")
    lines.append("")

    gs = content.get("gate_summary", {})
    if gs:
        pct = gs.get("pct", 0)
        lines.append(f"## Gate Summary")
        lines.append("")
        lines.append(f"| Passed | Failed | Total | Pass Rate |")
        lines.append(f"|--------|--------|-------|-----------|")
        lines.append(f"| {gs.get('passed', 0)} | {gs.get('failed', 0)} | {gs.get('total', 0)} | {pct}% |")
        lines.append("")

    gates = content.get("gates", [])
    if gates:
        lines.append("## Gate Results")
        lines.append("")
        lines.append("| Rule | Status | Message |")
        lines.append("|------|--------|---------|")
        for g in gates:
            status_icon = "PASS" if g.get("status") == "pass" else "FAIL"
            lines.append(f"| {g.get('rule', '?')} | {status_icon} | {g.get('message', '')} |")
        lines.append("")

    blockers = content.get("blockers", [])
    if blockers:
        lines.append("## Blockers")
        lines.append("")
        for b in blockers:
            lines.append(f"- {b}")
        lines.append("")

    return "\n".join(lines)


def _render_elevation_audit_md(content: dict) -> str:
    lines: list[str] = []
    project_id = content.get("project_id", "?")
    lines.append(f"# Elevation Audit Report: {project_id}")
    lines.append("")
    lines.append(f"**Current Environment:** {content.get('current_environment', '?')}")
    lines.append(f"**Generated At:** {content.get('generated_at', '')}")
    lines.append("")

    promotions = content.get("promotions", [])
    if promotions:
        lines.append("## Promotion History")
        lines.append("")
        lines.append("| History ID | From | To | Promoted By | Promoted At |")
        lines.append("|------------|------|----|-------------|-------------|")
        for p in promotions:
            lines.append(
                f"| {p.get('history_id', '?')} | {p.get('source_environment', '?')} "
                f"| {p.get('target_environment', '?')} | {p.get('promoted_by', '?')} "
                f"| {p.get('promoted_at', '?')} |"
            )
        lines.append("")
    else:
        lines.append("No promotion history found.")
        lines.append("")

    return "\n".join(lines)


def _render_findings_remediation_md(content: dict) -> str:
    lines: list[str] = []
    project_id = content.get("project_id", "?")
    lines.append(f"# Findings Remediation Report: {project_id}")
    lines.append("")
    lines.append(f"**Generated At:** {content.get('generated_at', '')}")
    lines.append("")

    summary = content.get("summary", {})
    if summary:
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Total Findings:** {summary.get('total', 0)}")
        lines.append(f"- **Resolved:** {summary.get('resolved_pct', 0)}%")
        lines.append("")

        lines.append("### By Severity")
        lines.append("")
        lines.append("| Severity | Count |")
        lines.append("|----------|-------|")
        for sev, count in summary.get("by_severity", {}).items():
            lines.append(f"| {sev.capitalize()} | {count} |")
        lines.append("")

        lines.append("### By Status")
        lines.append("")
        lines.append("| Status | Count |")
        lines.append("|--------|-------|")
        for status, count in summary.get("by_status", {}).items():
            lines.append(f"| {status.capitalize()} | {count} |")
        lines.append("")

    findings = content.get("findings", [])
    if findings:
        lines.append("## Findings")
        lines.append("")
        lines.append("| ID | Title | Severity | Source | Status |")
        lines.append("|----|-------|----------|--------|--------|")
        for f in findings:
            lines.append(
                f"| `{f.get('finding_id', '?')}` | {f.get('title', '?')} "
                f"| {f.get('severity', '?')} | {f.get('source_tool', '?')} "
                f"| {f.get('status', '?')} |"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# MinIO PDF upload helper
# ---------------------------------------------------------------------------


async def _upload_pdf_artifact(
    report_id: str, project_id: str, report_type: str, pdf_bytes: bytes
) -> str | None:
    """Upload PDF bytes to MinIO. Returns presigned URL or None on failure."""
    try:
        import aioboto3
        from pearl.config import settings

        session = aioboto3.Session()
        key = f"reports/{project_id}/pdf/{report_id}.pdf"

        async with session.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        ) as s3:
            await s3.put_object(
                Bucket=settings.s3_bucket,
                Key=key,
                Body=pdf_bytes,
                ContentType="application/pdf",
            )
            url = await s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket, "Key": key},
                ExpiresIn=settings.report_url_ttl_days * 86400,
            )
            return url
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("MinIO PDF upload failed: %s", e)
        return None
