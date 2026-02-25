"""Job status polling endpoint."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.models.job import JobStatusModel
from pearl.repositories.job_repo import JobRepository

router = APIRouter(tags=["Jobs"])


@router.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = JobRepository(db)
    row = await repo.get(job_id)
    if not row:
        raise NotFoundError("Job", job_id)

    return JobStatusModel(
        schema_version=row.schema_version,
        job_id=row.job_id,
        status=row.status,
        job_type=row.job_type,
        project_id=row.project_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        trace_id=row.trace_id,
        result_refs=row.result_refs,
        errors=row.errors,
    ).model_dump(mode="json", exclude_none=True)
