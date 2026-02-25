"""Finding repository."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.finding import FindingBatchRow, FindingRow
from pearl.repositories.base import BaseRepository


class FindingRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FindingRow)

    async def get(self, finding_id: str) -> FindingRow | None:
        return await self.get_by_id("finding_id", finding_id)

    async def get_by_ids(self, finding_ids: list[str]) -> list[FindingRow]:
        stmt = select(FindingRow).where(FindingRow.finding_id.in_(finding_ids))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _base_query(
        self,
        project_id: str,
        severity: str | None = None,
        status: str | None = None,
        category: str | None = None,
    ):
        """Build the base WHERE clause for project findings (excludes 'closed' markers)."""
        conditions = [
            FindingRow.project_id == project_id,
            FindingRow.status != "closed",
        ]
        if severity:
            conditions.append(FindingRow.severity == severity)
        if status:
            conditions.append(FindingRow.status == status)
        if category:
            conditions.append(FindingRow.category == category)
        return conditions

    async def list_by_project(
        self,
        project_id: str,
        severity: str | None = None,
        status: str | None = None,
        category: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[FindingRow]:
        conditions = self._base_query(project_id, severity, status, category)
        stmt = (
            select(FindingRow)
            .where(*conditions)
            .order_by(FindingRow.detected_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_project(
        self,
        project_id: str,
        severity: str | None = None,
        status: str | None = None,
        category: str | None = None,
    ) -> int:
        conditions = self._base_query(project_id, severity, status, category)
        stmt = select(func.count(FindingRow.finding_id)).where(*conditions)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def severity_counts(self, project_id: str) -> dict[str, int]:
        """Return counts by severity for all open findings (for summary cards)."""
        stmt = (
            select(FindingRow.severity, func.count(FindingRow.finding_id))
            .where(
                FindingRow.project_id == project_id,
                FindingRow.status != "closed",
            )
            .group_by(FindingRow.severity)
        )
        result = await self.session.execute(stmt)
        return dict(result.all())


class FindingBatchRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, FindingBatchRow)

    async def get(self, batch_id: str) -> FindingBatchRow | None:
        return await self.get_by_id("batch_id", batch_id)
