"""Repositories for client-pushed governance telemetry."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.governance_telemetry import ClientAuditEventRow, ClientCostEntryRow
from pearl.repositories.base import BaseRepository


class ClientAuditEventRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ClientAuditEventRow)

    async def list_by_project(self, project_id: str) -> list[ClientAuditEventRow]:
        return await self.list_by_field("project_id", project_id)

    async def list_since(
        self, project_id: str, since: datetime
    ) -> list[ClientAuditEventRow]:
        stmt = select(ClientAuditEventRow).where(
            ClientAuditEventRow.project_id == project_id,
            ClientAuditEventRow.timestamp >= since,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def bulk_create(self, rows: list[dict]) -> int:
        """Insert multiple audit events. Returns count of created rows."""
        created = 0
        for row_data in rows:
            row = ClientAuditEventRow(**row_data)
            self.session.add(row)
            created += 1
        await self.session.flush()
        return created


class ClientCostEntryRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ClientCostEntryRow)

    async def list_by_project(self, project_id: str) -> list[ClientCostEntryRow]:
        return await self.list_by_field("project_id", project_id)

    async def bulk_create(self, rows: list[dict]) -> int:
        """Insert multiple cost entries. Returns count of created rows."""
        created = 0
        for row_data in rows:
            row = ClientCostEntryRow(**row_data)
            self.session.add(row)
            created += 1
        await self.session.flush()
        return created
