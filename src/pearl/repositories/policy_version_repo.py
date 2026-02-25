"""Repository for PolicyVersion records."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.policy_version import PolicyVersionRow
from pearl.repositories.base import BaseRepository


class PolicyVersionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PolicyVersionRow)

    async def list_for_resource(
        self,
        resource_type: str,
        resource_id: str,
        limit: int = 50,
    ) -> list[PolicyVersionRow]:
        stmt = (
            select(PolicyVersionRow)
            .where(
                PolicyVersionRow.resource_type == resource_type,
                PolicyVersionRow.resource_id == resource_id,
            )
            .order_by(PolicyVersionRow.version_number.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_version_number(self, resource_type: str, resource_id: str) -> int:
        rows = await self.list_for_resource(resource_type, resource_id, limit=1)
        if rows:
            return rows[0].version_number
        return 0
