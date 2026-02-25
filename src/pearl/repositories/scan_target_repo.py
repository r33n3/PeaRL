"""Scan target repository."""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.scan_target import ScanTargetRow
from pearl.repositories.base import BaseRepository


class ScanTargetRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ScanTargetRow)

    async def get(self, scan_target_id: str) -> ScanTargetRow | None:
        return await self.get_by_id("scan_target_id", scan_target_id)

    async def list_by_project(self, project_id: str) -> list[ScanTargetRow]:
        return await self.list_by_field("project_id", project_id)

    async def list_by_tool_type(
        self,
        tool_type: str,
        status: str = "active",
    ) -> list[ScanTargetRow]:
        """Discovery: find all targets for a given tool type and status."""
        stmt = select(ScanTargetRow).where(
            and_(
                ScanTargetRow.tool_type == tool_type,
                ScanTargetRow.status == status,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_natural_key(
        self,
        project_id: str,
        repo_url: str,
        tool_type: str,
        branch: str,
    ) -> ScanTargetRow | None:
        """Check for existing target by natural key (for upsert/uniqueness)."""
        stmt = select(ScanTargetRow).where(
            and_(
                ScanTargetRow.project_id == project_id,
                ScanTargetRow.repo_url == repo_url,
                ScanTargetRow.tool_type == tool_type,
                ScanTargetRow.branch == branch,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
