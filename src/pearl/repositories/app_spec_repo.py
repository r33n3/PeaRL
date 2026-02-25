"""ApplicationSpec repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.app_spec import AppSpecRow
from pearl.repositories.base import BaseRepository


class AppSpecRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, AppSpecRow)

    async def get(self, app_id: str) -> AppSpecRow | None:
        return await self.get_by_id("app_id", app_id)

    async def get_by_project(self, project_id: str) -> AppSpecRow | None:
        stmt = select(AppSpecRow).where(AppSpecRow.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
