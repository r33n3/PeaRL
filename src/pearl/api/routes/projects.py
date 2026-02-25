"""Project CRUD API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError, ValidationError
from pearl.models.common import TraceabilityRef
from pearl.models.project import Project
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Projects"])


@router.post("/projects", status_code=201)
async def create_project(
    project: Project,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    repo = ProjectRepository(db)

    # Check for duplicate
    existing = await repo.get(project.project_id)
    if existing:
        raise ValidationError(f"Project '{project.project_id}' already exists")

    now = datetime.now(timezone.utc)
    project.created_at = now
    project.updated_at = now
    project.traceability = TraceabilityRef(trace_id=trace_id, source_refs=["api:/projects"])

    await repo.create(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        owner_team=project.owner_team,
        business_criticality=project.business_criticality,
        external_exposure=project.external_exposure,
        ai_enabled=project.ai_enabled,
        schema_version=project.schema_version,
    )
    await db.commit()
    return project.model_dump(mode="json", exclude_none=True)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    return Project(
        schema_version=row.schema_version,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        owner_team=row.owner_team,
        business_criticality=row.business_criticality,
        external_exposure=row.external_exposure,
        ai_enabled=row.ai_enabled,
        created_at=row.created_at,
        updated_at=row.updated_at,
    ).model_dump(mode="json", exclude_none=True)


@router.put("/projects/{project_id}")
async def update_project(
    project_id: str,
    project: Project,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    now = datetime.now(timezone.utc)
    await repo.update(
        row,
        name=project.name,
        description=project.description,
        owner_team=project.owner_team,
        business_criticality=project.business_criticality,
        external_exposure=project.external_exposure,
        ai_enabled=project.ai_enabled,
    )
    row.updated_at = now
    await db.commit()

    return Project(
        schema_version=row.schema_version,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        owner_team=row.owner_team,
        business_criticality=row.business_criticality,
        external_exposure=row.external_exposure,
        ai_enabled=row.ai_enabled,
        created_at=row.created_at,
        updated_at=now,
    ).model_dump(mode="json", exclude_none=True)


@router.get("/projects/{project_id}/summary")
async def get_project_summary(
    project_id: str,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a project governance summary in markdown or JSON."""
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.repositories.promotion_repo import PromotionEvaluationRepository
    from pearl.repositories.fairness_repo import (
        EvidencePackageRepository,
        FairnessCaseRepository,
        FairnessExceptionRepository,
        FairnessRequirementsSpecRepository,
        MonitoringSignalRepository,
    )
    from pearl.services.markdown_renderer import render_project_summary

    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    project_data = {
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "owner_team": row.owner_team,
        "business_criticality": row.business_criticality,
        "external_exposure": row.external_exposure,
        "ai_enabled": row.ai_enabled,
    }

    # Findings by severity
    finding_repo = FindingRepository(db)
    all_findings = await finding_repo.list_by_field("project_id", project_id)
    findings_by_severity: dict[str, int] = {}
    for f in all_findings:
        sev = f.severity or "unknown"
        findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1

    # Promotion readiness
    promotion = None
    try:
        eval_repo = PromotionEvaluationRepository(db)
        latest = await eval_repo.get_latest_by_project(project_id)
        if latest:
            promotion = {
                "source_environment": latest.source_environment,
                "target_environment": latest.target_environment,
                "status": latest.status,
                "passed_count": latest.passed_count,
                "failed_count": latest.failed_count,
                "total_count": latest.total_count,
                "progress_pct": latest.progress_pct,
                "blockers": latest.blockers,
                "rule_results": latest.rule_results,
                "evaluated_at": latest.evaluated_at.isoformat() if latest.evaluated_at else None,
            }
    except Exception:
        pass

    # Fairness posture
    fairness = None
    if row.ai_enabled:
        try:
            fc_repo = FairnessCaseRepository(db)
            fc = await fc_repo.get_by_project(project_id)
            frs_repo = FairnessRequirementsSpecRepository(db)
            frs = await frs_repo.get_by_project(project_id)
            ev_repo = EvidencePackageRepository(db)
            ev_list = await ev_repo.list_by_project(project_id)
            exc_repo = FairnessExceptionRepository(db)
            exc_list = await exc_repo.get_active_by_project(project_id)

            fairness = {}
            if fc:
                fairness["fairness_case"] = {
                    "fc_id": fc.fc_id,
                    "risk_tier": fc.risk_tier,
                    "fairness_criticality": fc.fairness_criticality,
                }
            if frs:
                fairness["requirements"] = frs.requirements or []
            if ev_list:
                latest_ev = ev_list[0]
                fairness["evidence"] = {
                    "evidence_id": latest_ev.evidence_id,
                    "attestation_status": latest_ev.attestation_status,
                }
            if exc_list:
                fairness["exceptions"] = [
                    {"exception_id": e.exception_id, "reason": (e.compensating_controls or {}).get("reason", ""), "status": e.status}
                    for e in exc_list
                ]
        except Exception:
            pass

    if format == "markdown":
        md = render_project_summary(
            project=project_data,
            findings_by_severity=findings_by_severity if findings_by_severity else None,
            promotion=promotion,
            fairness=fairness,
        )
        return {"format": "markdown", "content": md}

    return {
        "format": "json",
        "project": project_data,
        "findings_by_severity": findings_by_severity,
        "promotion_readiness": promotion,
        "fairness": fairness,
    }
