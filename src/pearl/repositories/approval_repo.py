"""Approval repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.approval import ApprovalDecisionRow, ApprovalRequestRow
from pearl.repositories.base import BaseRepository


class ApprovalRequestRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ApprovalRequestRow)

    async def get(self, approval_request_id: str) -> ApprovalRequestRow | None:
        return await self.get_by_id("approval_request_id", approval_request_id)

    async def list_by_project(self, project_id: str) -> list[ApprovalRequestRow]:
        return await self.list_by_field("project_id", project_id)

    async def list_by_status(self, status: str) -> list[ApprovalRequestRow]:
        return await self.list_by_field("status", status)

    async def list_by_statuses(self, statuses: list[str]) -> list[ApprovalRequestRow]:
        """List approval requests matching any of the given statuses."""
        stmt = select(ApprovalRequestRow).where(
            ApprovalRequestRow.status.in_(statuses)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class ApprovalDecisionRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ApprovalDecisionRow)
