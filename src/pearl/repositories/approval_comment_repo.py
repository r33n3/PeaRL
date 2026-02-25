"""Approval comment repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.approval_comment import ApprovalCommentRow
from pearl.repositories.base import BaseRepository


class ApprovalCommentRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ApprovalCommentRow)

    async def get(self, comment_id: str) -> ApprovalCommentRow | None:
        return await self.get_by_id("comment_id", comment_id)

    async def list_by_approval(self, approval_request_id: str) -> list[ApprovalCommentRow]:
        stmt = (
            select(ApprovalCommentRow)
            .where(ApprovalCommentRow.approval_request_id == approval_request_id)
            .order_by(ApprovalCommentRow.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
