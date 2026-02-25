"""Context compilation API routes."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.models.compiled_context import CompiledContextPackage
from pearl.repositories.compiled_package_repo import CompiledPackageRepository
from pearl.services.compiler.context_compiler import compile_context
from pearl.workers.queue import enqueue_job

router = APIRouter(tags=["ContextCompile"])


@router.post("/projects/{project_id}/compile-context", status_code=202)
async def compile_context_endpoint(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    body = await request.json()
    compile_options = body.get("compile_options", {})

    # For simplicity, run compilation synchronously but return 202 pattern
    # In production, this would enqueue to Redis and return immediately
    try:
        package = await compile_context(
            project_id=project_id,
            trace_id=trace_id,
            apply_exceptions=compile_options.get("apply_active_exceptions", True),
            session=db,
        )
        await db.commit()

        # Create a job record for tracking
        job = await enqueue_job(
            session=db,
            job_type="compile_context",
            project_id=project_id,
            trace_id=trace_id,
        )
        # Mark as already succeeded since we ran synchronously
        from pearl.repositories.job_repo import JobRepository
        from datetime import datetime, timezone
        job_repo = JobRepository(db)
        job_row = await job_repo.get(job.job_id)
        if job_row:
            job_row.status = "succeeded"
            job_row.result_refs = [{"ref_id": package.package_metadata.package_id,
                                   "kind": "artifact", "summary": "Compiled context package"}]
            job_row.updated_at = datetime.now(timezone.utc)
        await db.commit()

        return job.model_dump(mode="json", exclude_none=True)
    except Exception as e:
        # If compilation fails, still create a failed job
        job = await enqueue_job(
            session=db,
            job_type="compile_context",
            project_id=project_id,
            trace_id=trace_id,
        )
        from pearl.repositories.job_repo import JobRepository
        from datetime import datetime, timezone
        job_repo = JobRepository(db)
        job_row = await job_repo.get(job.job_id)
        if job_row:
            job_row.status = "failed"
            job_row.errors = [{"code": "COMPILE_ERROR", "message": str(e),
                              "trace_id": trace_id,
                              "timestamp": datetime.now(timezone.utc).isoformat()}]
            job_row.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise


@router.get("/projects/{project_id}/compiled-package")
async def get_compiled_package(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = CompiledPackageRepository(db)
    row = await repo.get_latest_by_project(project_id)
    if not row:
        raise NotFoundError("Compiled package", project_id)

    return row.package_data
