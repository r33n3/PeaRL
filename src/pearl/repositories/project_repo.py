"""Project repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.project import ProjectRow
from pearl.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectRow)

    async def get(self, project_id: str) -> ProjectRow | None:
        return await self.get_by_id("project_id", project_id)
