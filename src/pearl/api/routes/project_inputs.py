"""Project sub-resource attachment routes (org-baseline, app-spec, environment-profile)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.models.app_spec import ApplicationSpec
from pearl.models.environment_profile import EnvironmentProfile
from pearl.models.org_baseline import OrgBaseline
from pearl.repositories.app_spec_repo import AppSpecRepository
from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
from pearl.repositories.org_baseline_repo import OrgBaselineRepository
from pearl.repositories.project_repo import ProjectRepository

router = APIRouter(tags=["Projects"])


async def _ensure_project_exists(project_id: str, db: AsyncSession):
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)
    return row


@router.get("/projects/{project_id}/org-baseline")
async def get_org_baseline(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch the org baseline for a project."""
    await _ensure_project_exists(project_id, db)
    repo = OrgBaselineRepository(db)
    row = await repo.get_by_project(project_id)
    if not row:
        raise NotFoundError("OrgBaseline", project_id)
    return {
        "baseline_id": row.baseline_id,
        "project_id": row.project_id,
        "org_name": row.org_name,
        "defaults": row.defaults,
        "environment_defaults": row.environment_defaults,
        "schema_version": row.schema_version,
    }


@router.post("/projects/{project_id}/org-baseline")
async def upsert_org_baseline(
    project_id: str,
    baseline: OrgBaseline,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    await _ensure_project_exists(project_id, db)
    repo = OrgBaselineRepository(db)

    existing = await repo.get_by_project(project_id)
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
            project_id=project_id,
            org_name=baseline.org_name,
            defaults=defaults_dict,
            environment_defaults=env_defaults,
            integrity=integrity_dict,
            schema_version=baseline.schema_version,
        )

    await db.commit()
    return baseline.model_dump(mode="json", exclude_none=True)


@router.post("/projects/{project_id}/app-spec")
async def upsert_app_spec(
    project_id: str,
    spec: ApplicationSpec,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    await _ensure_project_exists(project_id, db)
    repo = AppSpecRepository(db)

    full_spec = spec.model_dump(mode="json", exclude_none=True)
    integrity_dict = spec.integrity.model_dump(mode="json", exclude_none=True) if spec.integrity else None
    app_id = spec.application.app_id

    existing = await repo.get_by_project(project_id)
    if existing:
        await repo.update(existing, app_id=app_id, full_spec=full_spec, integrity=integrity_dict)
    else:
        await repo.create(
            app_id=app_id,
            project_id=project_id,
            full_spec=full_spec,
            integrity=integrity_dict,
            schema_version=spec.schema_version,
        )

    await db.commit()
    return full_spec


@router.post("/projects/{project_id}/environment-profile")
async def upsert_environment_profile(
    project_id: str,
    profile: EnvironmentProfile,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    await _ensure_project_exists(project_id, db)
    repo = EnvironmentProfileRepository(db)

    integrity_dict = profile.integrity.model_dump(mode="json", exclude_none=True) if profile.integrity else None

    existing = await repo.get_by_project(project_id)
    if existing:
        await repo.update(
            existing,
            profile_id=profile.profile_id,
            environment=profile.environment,
            delivery_stage=profile.delivery_stage,
            risk_level=profile.risk_level,
            autonomy_mode=profile.autonomy_mode,
            allowed_capabilities=profile.allowed_capabilities,
            blocked_capabilities=profile.blocked_capabilities,
            approval_level=profile.approval_level,
            integrity=integrity_dict,
        )
    else:
        await repo.create(
            profile_id=profile.profile_id,
            project_id=project_id,
            environment=profile.environment,
            delivery_stage=profile.delivery_stage,
            risk_level=profile.risk_level,
            autonomy_mode=profile.autonomy_mode,
            allowed_capabilities=profile.allowed_capabilities,
            blocked_capabilities=profile.blocked_capabilities,
            approval_level=profile.approval_level,
            integrity=integrity_dict,
            schema_version=profile.schema_version,
        )

    await db.commit()
    return profile.model_dump(mode="json", exclude_none=True)
