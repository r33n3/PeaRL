"""Org-wide baseline routes — GET/POST /org/baseline."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import RequireAdmin, get_current_user, get_db
from pearl.errors.exceptions import NotFoundError
from pearl.models.org_baseline import OrgBaseline
from pearl.repositories.org_baseline_repo import OrgBaselineRepository

router = APIRouter(prefix="/org", tags=["Org Baseline"])


@router.get("/baseline")
async def get_org_baseline(db: AsyncSession = Depends(get_db)) -> dict:
    """Return the org-wide baseline (project_id IS NULL)."""
    repo = OrgBaselineRepository(db)
    row = await repo.get_org_wide()
    if not row:
        raise NotFoundError("OrgBaseline", "org-wide")
    return {
        "baseline_id": row.baseline_id,
        "project_id": row.project_id,
        "org_id": row.org_id,
        "org_name": row.org_name,
        "defaults": row.defaults,
        "environment_defaults": row.environment_defaults,
        "schema_version": row.schema_version,
    }


@router.get("/baseline/controls")
async def get_baseline_controls(_current_user: dict = Depends(get_current_user)) -> dict:
    """Return the full AIUC1 control registry with labels and mandatory sets per tier."""
    from pearl.scanning.baseline_package import (
        AIUC1_CONTROLS,
        ESSENTIAL_BASELINE,
        AI_STANDARD_BASELINE,
        AI_COMPREHENSIVE_BASELINE,
    )

    def mandatory_set(baseline: dict) -> list[str]:
        """Return control keys (domain.control_id) that are True in this baseline tier."""
        result = []
        for domain, controls in baseline.get("defaults", {}).items():
            for ctrl_id, enabled in controls.items():
                if enabled is True:
                    result.append(f"{domain}.{ctrl_id}")
        return result

    return {
        "controls": AIUC1_CONTROLS,
        "mandatory": {
            "essential": mandatory_set(ESSENTIAL_BASELINE),
            "ai_standard": mandatory_set(AI_STANDARD_BASELINE),
            "ai_comprehensive": mandatory_set(AI_COMPREHENSIVE_BASELINE),
        },
    }


@router.post("/baseline")
async def upsert_org_baseline(
    baseline: OrgBaseline,
    db: AsyncSession = Depends(get_db),
    _admin: dict = RequireAdmin,
) -> dict:
    """Upsert the org-wide baseline (project_id = None, org_id = 'default')."""
    repo = OrgBaselineRepository(db)
    existing = await repo.get_org_wide()

    defaults_dict = baseline.defaults.model_dump(mode="json", exclude_none=True)
    env_defaults = baseline.environment_defaults
    integrity_dict = baseline.integrity.model_dump(mode="json", exclude_none=True) if baseline.integrity else None

    if existing:
        await repo.update(
            existing,
            baseline_id=baseline.baseline_id,
            org_name=baseline.org_name,
            defaults=defaults_dict,
            environment_defaults=env_defaults,
            integrity=integrity_dict,
        )
    else:
        await repo.create(
            baseline_id=baseline.baseline_id,
            project_id=None,
            org_id="default",
            org_name=baseline.org_name,
            defaults=defaults_dict,
            environment_defaults=env_defaults,
            integrity=integrity_dict,
            schema_version=baseline.schema_version,
        )

    await db.commit()
    return baseline.model_dump(mode="json", exclude_none=True)
