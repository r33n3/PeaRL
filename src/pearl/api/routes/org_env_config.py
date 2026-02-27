"""Org Environment Config API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import ValidationError
from pearl.repositories.org_env_config_repo import OrgEnvironmentConfigRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["OrgEnvironmentConfig"])


@router.get("/org-env-config")
async def get_org_env_config(
    org_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get the environment ladder config for an org."""
    repo = OrgEnvironmentConfigRepository(db)
    config = await repo.get_by_org(org_id)
    if not config:
        return {"org_id": org_id, "stages": [], "config_id": None}
    return _config_dict(config)


@router.put("/org-env-config", status_code=200)
async def upsert_org_env_config(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upsert the environment ladder for an org."""
    org_id = body.get("org_id")
    stages = body.get("stages")
    if not org_id:
        raise ValidationError("org_id is required")
    if stages is None:
        raise ValidationError("stages is required")
    if not isinstance(stages, list):
        raise ValidationError("stages must be a list")

    repo = OrgEnvironmentConfigRepository(db)
    config_id = body.get("config_id") or generate_id("envconf_")
    config = await repo.upsert(config_id=config_id, org_id=org_id, stages=stages)
    await db.commit()
    return _config_dict(config)


def _config_dict(config) -> dict:
    return {
        "config_id": config.config_id,
        "org_id": config.org_id,
        "stages": config.stages or [],
        "created_at": config.created_at.isoformat() if config.created_at else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }
