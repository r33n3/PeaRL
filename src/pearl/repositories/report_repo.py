"""Report repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.report import ReportRow
from pearl.repositories.base import BaseRepository


class ReportRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ReportRow)

    async def get(self, report_id: str) -> ReportRow | None:
        return await self.get_by_id("report_id", report_id)

    async def list_by_project(self, project_id: str) -> list[ReportRow]:
        return await self.list_by_field("project_id", project_id)
