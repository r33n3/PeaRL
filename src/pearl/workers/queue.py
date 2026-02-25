"""Job queue management using Redis or in-process fallback."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.job import JobRow
from pearl.models.job import JobStatusModel
from pearl.repositories.job_repo import JobRepository
from pearl.services.id_generator import generate_id


async def enqueue_job(
    session: AsyncSession,
    job_type: str,
    project_id: str | None,
    trace_id: str,
    payload: dict | None = None,
    redis=None,
) -> JobStatusModel:
    """Create a job record and optionally enqueue to Redis.

    Returns a JobStatusModel with status='queued'.
    """
    job_id = generate_id("job_")
    now = datetime.now(timezone.utc)

    repo = JobRepository(session)
    await repo.create(
        job_id=job_id,
        job_type=job_type,
        project_id=project_id,
        status="queued",
        trace_id=trace_id,
        result_refs=[],
        errors=None,
    )
    await session.flush()

    # Enqueue to Redis if available
    if redis:
        import json
        await redis.rpush(
            f"pearl:jobs:{job_type}",
            json.dumps({"job_id": job_id, "payload": payload or {}}),
        )

    return JobStatusModel(
        schema_version="1.1",
        job_id=job_id,
        status="queued",
        job_type=job_type,
        project_id=project_id,
        created_at=now,
        updated_at=now,
        trace_id=trace_id,
        result_refs=[],
    )
