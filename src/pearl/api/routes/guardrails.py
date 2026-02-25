"""Guardrails API routes — list, get details, get recommendations."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.project_repo import ProjectRepository
from pearl.scanning.policy.guardrails import get_default_guardrails
from pearl.scanning.types import GuardrailType

router = APIRouter(tags=["Guardrails"])

_registry = get_default_guardrails()


@router.get("/guardrails", status_code=200)
async def list_guardrails(
    category: str | None = Query(None, description="Filter by guardrail type category"),
    severity: str | None = Query(None, description="Filter by severity"),
) -> list[dict]:
    """List all guardrails with optional filtering."""
    if category:
        try:
            gt = GuardrailType(category)
            guardrails = _registry.get_by_type(gt)
        except ValueError:
            guardrails = []
    elif severity:
        guardrails = _registry.get_by_severity(severity)
    else:
        guardrails = _registry.get_all()

    return [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "category": g.guardrail_type.value,
            "severity": g.severity.value,
            "implementation_steps": g.implementation_steps,
        }
        for g in guardrails
    ]


@router.get("/guardrails/{guardrail_id}", status_code=200)
async def get_guardrail(guardrail_id: str) -> dict:
    """Get guardrail detail with code examples."""
    guardrail = _registry.get(guardrail_id)
    if not guardrail:
        raise NotFoundError("Guardrail", guardrail_id)

    return {
        "id": guardrail.id,
        "name": guardrail.name,
        "description": guardrail.description,
        "category": guardrail.guardrail_type.value,
        "severity": guardrail.severity.value,
        "implementation_steps": guardrail.implementation_steps,
        "code_examples": guardrail.code_examples,
        "mitigates_categories": [c.value for c in guardrail.mitigates_categories],
    }


@router.get("/projects/{project_id}/recommended-guardrails", status_code=200)
async def get_recommended_guardrails(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get guardrails recommended for a project based on its findings."""
    from sqlalchemy import select
    from pearl.db.models.finding import FindingRow
    from pearl.scanning.service import ScanningService
    from pearl.scanning.analyzers.base import AnalyzerFinding
    from pearl.scanning.types import ScanSeverity, AttackCategory, ComponentType

    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    # Get open findings for the project
    stmt = (
        select(FindingRow)
        .where(FindingRow.project_id == project_id)
        .where(FindingRow.status == "open")
    )
    result = await db.execute(stmt)
    findings = list(result.scalars().all())

    # Convert to AnalyzerFinding-like objects for the service
    analyzer_findings = []
    for f in findings:
        try:
            analyzer_findings.append(AnalyzerFinding(
                title=f.title,
                description=f.full_data.get("description", "") if f.full_data else "",
                severity=ScanSeverity.MEDIUM,
                category=AttackCategory.PROMPT_INJECTION,
                component_type=ComponentType.CODE,
                component_name="",
            ))
        except Exception:
            pass

    service = ScanningService()
    recommended = service.recommend_guardrails(analyzer_findings)

    return {
        "project_id": project_id,
        "open_findings_count": len(findings),
        "recommended_guardrails": [
            {
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "category": g.guardrail_type.value,
                "severity": g.severity.value,
                "implementation_steps": g.implementation_steps,
                "code_examples": g.code_examples,
            }
            for g in recommended
        ],
    }
