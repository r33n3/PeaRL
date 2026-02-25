"""Job repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.job import JobRow
from pearl.repositories.base import BaseRepository


class JobRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, JobRow)

    async def get(self, job_id: str) -> JobRow | None:
        return await self.get_by_id("job_id", job_id)
