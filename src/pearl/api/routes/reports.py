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
    try:
        from pearl.repositories.finding_repo import FindingRepository

        finding_repo = FindingRepository(db)
        all_findings = await finding_repo.list_by_field("project_id", project_id)
        findings_by_severity: dict[str, int] = {}
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
