"""Compliance assessment API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.project_repo import ProjectRepository
from pearl.scanning.baseline_package import (
    get_all_baselines,
    get_recommended_baseline,
    select_baseline_tier,
)
from pearl.scanning.policy.templates import get_policy_templates

router = APIRouter(tags=["Compliance"])


@router.get("/projects/{project_id}/compliance-assessment", status_code=200)
async def get_compliance_assessment(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get compliance assessment for a project based on its findings."""
    from sqlalchemy import select
    from pearl.db.models.finding import FindingRow
    from pearl.scanning.compliance.assessor import ComplianceAssessor
    from pearl.scanning.types import AttackCategory, ScanSeverity

    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    # Get all findings for the project
    stmt = (
        select(FindingRow)
        .where(FindingRow.project_id == project_id)
        .where(FindingRow.status == "open")
    )
    result = await db.execute(stmt)
    findings = list(result.scalars().all())

    # Convert to assessment format
    finding_dicts = []
    for f in findings:
        # Try to extract category from full_data
        full = f.full_data or {}
        cat_str = full.get("category", f.category)
        sev_str = full.get("severity", f.severity)

        # Map to scanning types
        try:
            cat = AttackCategory(cat_str)
        except ValueError:
            cat = cat_str
        try:
            sev = ScanSeverity(sev_str)
        except ValueError:
            sev = sev_str

        finding_dicts.append({
            "category": cat,
            "severity": sev,
            "id": f.finding_id,
        })

    assessor = ComplianceAssessor()
    assessment = assessor.assess(finding_dicts, scan_id=f"assess_{project_id}")

    return {
        "project_id": project_id,
        "overall_score": assessment.overall_compliance_score,
        "total_findings": len(findings),
        "frameworks": {
            fw.value: {
                "score": fa.compliance_score,
                "total_requirements": fa.total_requirements,
                "compliant": fa.compliant_count,
                "non_compliant": fa.non_compliant_count,
                "requirements": [
                    {
                        "requirement_id": ra.requirement.id,
                        "status": ra.status.value,
                        "findings_count": len(ra.findings),
                    }
                    for ra in fa.requirements.values()
                ],
            }
            for fw, fa in assessment.frameworks.items()
        },
    }


@router.get("/baselines/recommended", status_code=200)
async def get_recommended_baselines(
    ai_enabled: bool = Query(True, description="Whether the project uses AI"),
    business_criticality: str = Query("moderate", description="Business criticality level"),
) -> dict:
    """Get the recommended baseline tier and all baselines."""
    tier = select_baseline_tier(ai_enabled, business_criticality)
    recommended = get_recommended_baseline(ai_enabled, business_criticality)
    all_baselines = get_all_baselines()

    return {
        "recommended_tier": tier,
        "recommended_baseline": recommended,
        "all_baselines": {
            name: {
                "tier": baseline["tier"],
                "baseline_id": baseline["baseline_id"],
                "org_name": baseline["org_name"],
                "defaults_sections": list(baseline["defaults"].keys()),
            }
            for name, baseline in all_baselines.items()
        },
    }


@router.get("/policy-templates", status_code=200)
async def list_policy_templates(
    category: str | None = Query(None, description="Filter by policy category"),
) -> list[dict]:
    """List AI security policy templates."""
    from pearl.scanning.types import PolicyCategory

    registry = get_policy_templates()
    if category:
        try:
            pc = PolicyCategory(category)
            templates = registry.get_by_category(pc)
        except ValueError:
            templates = []
    else:
        templates = registry.get_all()

    return [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "category": t.category.value,
            "rules_count": len(t.rules),
        }
        for t in templates
    ]


@router.get("/policy-templates/{template_id}", status_code=200)
async def get_policy_template(template_id: str) -> dict:
    """Get policy template detail with rules."""
    registry = get_policy_templates()
    template = registry.get(template_id)
    if not template:
        raise NotFoundError("PolicyTemplate", template_id)

    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category.value,
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "severity": r.severity.value,
                "condition": r.condition,
                "action": r.action,
            }
            for r in template.rules
        ],
    }
