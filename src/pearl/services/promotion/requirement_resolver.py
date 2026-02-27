"""Requirement resolver — merges Org baseline + BU framework requirements + Project constraints."""

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.repositories.business_unit_repo import BusinessUnitRepository
from pearl.repositories.framework_requirement_repo import FrameworkRequirementRepository
from pearl.repositories.org_baseline_repo import OrgBaselineRepository
from pearl.repositories.project_repo import ProjectRepository


class ResolvedRequirement(BaseModel):
    control_id: str
    framework: str
    requirement_level: str  # "mandatory" | "recommended"
    evidence_type: str
    source: str  # "org_baseline" | "bu_framework" | "project_profile"
    transition: str  # e.g. "sandbox->dev"


_LEVEL_ORDER = {"mandatory": 2, "recommended": 1}


def _higher_level(a: str, b: str) -> str:
    """Return the stricter of two requirement levels."""
    return a if _LEVEL_ORDER.get(a, 0) >= _LEVEL_ORDER.get(b, 0) else b


async def resolve_requirements(
    project_id: str,
    source_env: str,
    target_env: str,
    session: AsyncSession,
) -> list[ResolvedRequirement]:
    """Merge Org baseline + BU framework requirements + Project profile for a transition.

    Merging rules:
    - Org floor requirements are always included
    - BU requirements are added/merged on top (can only tighten, not weaken)
    - If the same control_id appears in multiple sources, the strictest level wins
    """
    transition = f"{source_env}->{target_env}"

    # Load project to get bu_id and org_id
    proj_repo = ProjectRepository(session)
    project = await proj_repo.get(project_id)
    if not project:
        return []

    # Collect requirements: control_id → ResolvedRequirement (strictest level wins)
    merged: dict[str, ResolvedRequirement] = {}

    def _add(control_id: str, framework: str, level: str, evidence_type: str, source: str):
        key = control_id
        if key in merged:
            existing = merged[key]
            new_level = _higher_level(existing.requirement_level, level)
            if new_level != existing.requirement_level:
                merged[key] = ResolvedRequirement(
                    control_id=control_id,
                    framework=framework,
                    requirement_level=new_level,
                    evidence_type=evidence_type,
                    source=source,
                    transition=transition,
                )
        else:
            merged[key] = ResolvedRequirement(
                control_id=control_id,
                framework=framework,
                requirement_level=level,
                evidence_type=evidence_type,
                source=source,
                transition=transition,
            )

    # 1. Org baseline floor requirements (derive from baseline.defaults if present)
    if project.org_id:
        baseline_repo = OrgBaselineRepository(session)
        baseline = await baseline_repo.get_by_project(project_id)
        if baseline and baseline.defaults:
            # Extract any framework requirement entries from baseline defaults
            floor_reqs = baseline.defaults.get("framework_requirements", [])
            for req in floor_reqs:
                _add(
                    control_id=req.get("control_id", ""),
                    framework=req.get("framework", "org_baseline"),
                    level=req.get("requirement_level", "mandatory"),
                    evidence_type=req.get("evidence_type", "attestation"),
                    source="org_baseline",
                )

    # 2. BU framework requirements
    bu_id = getattr(project, "bu_id", None)
    if bu_id:
        req_repo = FrameworkRequirementRepository(session)
        bu_reqs = await req_repo.get_by_bu_and_transition(bu_id, source_env, target_env)
        bu_repo = BusinessUnitRepository(session)
        bu = await bu_repo.get(bu_id)

        for req in bu_reqs:
            _add(
                control_id=req.control_id,
                framework=req.framework,
                level=req.requirement_level,
                evidence_type=req.evidence_type,
                source="bu_framework",
            )

    # Return sorted: mandatory first, then by control_id
    result = list(merged.values())
    result.sort(key=lambda r: (_LEVEL_ORDER.get(r.requirement_level, 0) * -1, r.control_id))
    return result
