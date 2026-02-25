"""OrgBaseline repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.org_baseline import OrgBaselineRow
from pearl.repositories.base import BaseRepository


class OrgBaselineRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, OrgBaselineRow)

    async def get(self, baseline_id: str) -> OrgBaselineRow | None:
        return await self.get_by_id("baseline_id", baseline_id)

    async def get_by_project(self, project_id: str) -> OrgBaselineRow | None:
        stmt = select(OrgBaselineRow).where(OrgBaselineRow.project_id == project_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
