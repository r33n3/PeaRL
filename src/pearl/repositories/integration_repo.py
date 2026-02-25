"""Repositories for integration endpoints and sync logs."""

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.integration import IntegrationEndpointRow, IntegrationSyncLogRow
from pearl.repositories.base import BaseRepository


class IntegrationEndpointRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, IntegrationEndpointRow)

    async def get(self, endpoint_id: str) -> IntegrationEndpointRow | None:
        return await self.get_by_id("endpoint_id", endpoint_id)

    async def list_by_project(self, project_id: str) -> list[IntegrationEndpointRow]:
        return await self.list_by_field("project_id", project_id)

    async def list_sources(self, project_id: str) -> list[IntegrationEndpointRow]:
        """List enabled source and bidirectional endpoints for a project."""
        stmt = select(IntegrationEndpointRow).where(
            and_(
                IntegrationEndpointRow.project_id == project_id,
                IntegrationEndpointRow.enabled.is_(True),
                IntegrationEndpointRow.integration_type.in_(["source", "bidirectional"]),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_sinks(self, project_id: str) -> list[IntegrationEndpointRow]:
        """List enabled sink and bidirectional endpoints for a project."""
        stmt = select(IntegrationEndpointRow).where(
            and_(
                IntegrationEndpointRow.project_id == project_id,
                IntegrationEndpointRow.enabled.is_(True),
                IntegrationEndpointRow.integration_type.in_(["sink", "bidirectional"]),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_name(
        self, project_id: str, name: str
    ) -> IntegrationEndpointRow | None:
        """Find an endpoint by project + name (for uniqueness checks)."""
        stmt = select(IntegrationEndpointRow).where(
            and_(
                IntegrationEndpointRow.project_id == project_id,
                IntegrationEndpointRow.name == name,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class IntegrationSyncLogRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, IntegrationSyncLogRow)

    async def list_by_endpoint(
        self, endpoint_id: str, limit: int = 50
    ) -> list[IntegrationSyncLogRow]:
        """List recent sync logs for an endpoint, newest first."""
        stmt = (
            select(IntegrationSyncLogRow)
            .where(IntegrationSyncLogRow.endpoint_id == endpoint_id)
            .order_by(IntegrationSyncLogRow.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create_log(
        self,
        log_id: str,
        endpoint_id: str,
        project_id: str,
        direction: str,
        status: str,
        records_processed: int,
        error_message: str | None = None,
    ) -> IntegrationSyncLogRow:
        """Create a sync log entry."""
        return await self.create(
            log_id=log_id,
            endpoint_id=endpoint_id,
            project_id=project_id,
            direction=direction,
            status=status,
            records_processed=records_processed,
            error_message=error_message,
        )
