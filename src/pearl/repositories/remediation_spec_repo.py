"""RemediationSpec repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.remediation_spec import RemediationSpecRow
from pearl.repositories.base import BaseRepository


class RemediationSpecRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, RemediationSpecRow)

    async def get(self, remediation_spec_id: str) -> RemediationSpecRow | None:
        return await self.get_by_id("remediation_spec_id", remediation_spec_id)
