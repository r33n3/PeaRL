"""Project requirements endpoint — merged resolved requirements for a transition."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.promotion.requirement_resolver import resolve_requirements

router = APIRouter(tags=["Requirements"])


@router.get("/projects/{project_id}/requirements")
async def get_project_requirements(
    project_id: str,
    source_env: str = "sandbox",
    target_env: str = "dev",
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return merged resolved requirements for a project's environment transition."""
    proj_repo = ProjectRepository(db)
    project = await proj_repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    requirements = await resolve_requirements(
        project_id=project_id,
        source_env=source_env,
        target_env=target_env,
        session=db,
    )
    return [r.model_dump() for r in requirements]
