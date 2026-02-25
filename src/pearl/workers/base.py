"""Base worker interface for async job processing."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.job import JobRow
from pearl.repositories.job_repo import JobRepository


class BaseWorker(ABC):
    """Abstract base class for job workers."""

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

        # Transition to running
        job.status = "running"
        job.updated_at = datetime.now(timezone.utc)
        await session.flush()

        try:
            result = await self.process(job_id, payload, session)
            job.status = "succeeded"
            job.result_refs = result.get("result_refs", [])
            job.errors = None
        except Exception as e:
            job.status = "failed"
            job.errors = [{"code": "WORKER_ERROR", "message": str(e),
                          "trace_id": job.trace_id,
                          "timestamp": datetime.now(timezone.utc).isoformat()}]

        job.updated_at = datetime.now(timezone.utc)
        await session.commit()
