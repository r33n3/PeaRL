"""Base worker interface for async job processing."""

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.repositories.job_repo import JobRepository

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """Abstract base class for job workers."""

    max_retries: int = 3

    @abstractmethod
    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        """Process a job and return result references.

        Returns:
            Dict with 'result_refs' list and optional 'errors' list.
        """
        ...

    async def execute(self, job_id: str, payload: dict, session: AsyncSession) -> None:
        """Execute the full job lifecycle: running -> process -> succeeded/failed."""
        repo = JobRepository(session)
        job = await repo.get(job_id)
        if not job:
            return

        retry_count = (payload or {}).get("_retry_count", 0)

        # Transition to running
        job.status = "running"
        job.updated_at = datetime.now(timezone.utc)
        await session.flush()

        try:
            result = await self.process(job_id, payload, session)
            job.status = "succeeded"
            job.result_refs = result.get("result_refs", [])
            job.errors = None
            logger.info("Job %s succeeded (type=%s)", job_id, job.job_type)
        except Exception as exc:
            error_detail = {
                "code": "WORKER_ERROR",
                "message": str(exc),
                "trace_id": job.trace_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "retry_count": retry_count,
            }
            logger.exception("Job %s failed (type=%s, retry=%d)", job_id, job.job_type, retry_count)

            if retry_count < self.max_retries:
                # Re-queue for retry
                job.status = "queued"
                job.errors = [error_detail]
                job.updated_at = datetime.now(timezone.utc)
                await session.commit()
                return
            else:
                job.status = "failed"
                job.errors = [error_detail]

        job.updated_at = datetime.now(timezone.utc)
        await session.commit()
