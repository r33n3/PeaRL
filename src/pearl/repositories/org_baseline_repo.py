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

    async def get_org_wide(self) -> OrgBaselineRow | None:
        """Return the org-level baseline (project_id IS NULL, bu_id IS NULL)."""
        stmt = (
            select(OrgBaselineRow)
            .where(OrgBaselineRow.project_id.is_(None))
            .where(OrgBaselineRow.bu_id.is_(None))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_by_bu(self, bu_id: str) -> OrgBaselineRow | None:
        """Return the BU-level baseline (bu_id set, project_id IS NULL)."""
        stmt = (
            select(OrgBaselineRow)
            .where(OrgBaselineRow.bu_id == bu_id)
            .where(OrgBaselineRow.project_id.is_(None))
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_for_project(self, project_id: str, bu_id: str | None = None) -> OrgBaselineRow | None:
        """Return baseline using 3-tier resolution: project → BU → org-wide."""
        row = await self.get_by_project(project_id)
        if row is None and bu_id:
            row = await self.get_by_bu(bu_id)
        if row is None:
            row = await self.get_org_wide()
        return row
