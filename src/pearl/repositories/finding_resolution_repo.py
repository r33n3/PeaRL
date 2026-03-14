"""FindingResolution repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.finding_resolution import FindingResolutionRow
from pearl.repositories.base import BaseRepository


class FindingResolutionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FindingResolutionRow)

    async def get_by_finding(self, finding_id: str) -> FindingResolutionRow | None:
        """Fetch the resolution record for a specific finding."""
        stmt = select(FindingResolutionRow).where(
            FindingResolutionRow.finding_id == finding_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_pending_rescan(self, project_id: str) -> list[FindingResolutionRow]:
        """Return all resolutions awaiting automatic rescan confirmation for a project."""
        stmt = select(FindingResolutionRow).where(
            FindingResolutionRow.project_id == project_id,
            FindingResolutionRow.approval_mode == "rescan",
            FindingResolutionRow.approval_status == "pending",
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
