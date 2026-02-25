"""EnvironmentProfile repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.environment_profile import EnvironmentProfileRow
from pearl.repositories.base import BaseRepository


class EnvironmentProfileRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, EnvironmentProfileRow)

    async def get(self, profile_id: str) -> EnvironmentProfileRow | None:
        return await self.get_by_id("profile_id", profile_id)

    async def get_by_project(self, project_id: str) -> EnvironmentProfileRow | None:
        stmt = select(EnvironmentProfileRow).where(EnvironmentProfileRow.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
