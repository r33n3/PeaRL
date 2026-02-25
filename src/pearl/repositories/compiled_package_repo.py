"""CompiledPackage repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.compiled_package import CompiledPackageRow
from pearl.repositories.base import BaseRepository


class CompiledPackageRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, CompiledPackageRow)

    async def get(self, package_id: str) -> CompiledPackageRow | None:
        return await self.get_by_id("package_id", package_id)

    async def get_latest_by_project(self, project_id: str) -> CompiledPackageRow | None:
        stmt = (
            select(CompiledPackageRow)
            .where(CompiledPackageRow.project_id == project_id)
            .order_by(CompiledPackageRow.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
