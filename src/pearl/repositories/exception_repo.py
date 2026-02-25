"""Exception repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.exception import ExceptionRecordRow
from pearl.repositories.base import BaseRepository


class ExceptionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ExceptionRecordRow)

    async def get(self, exception_id: str) -> ExceptionRecordRow | None:
        return await self.get_by_id("exception_id", exception_id)

    async def get_active_by_project(self, project_id: str) -> list[ExceptionRecordRow]:
        stmt = select(ExceptionRecordRow).where(
            ExceptionRecordRow.project_id == project_id,
            ExceptionRecordRow.status == "active",
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
