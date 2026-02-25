"""Notification repository."""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.notification import NotificationRow
from pearl.repositories.base import BaseRepository


class NotificationRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, NotificationRow)

    async def get(self, notification_id: str) -> NotificationRow | None:
        return await self.get_by_id("notification_id", notification_id)

    async def list_unread(self, recipient: str = "all", limit: int = 50) -> list[NotificationRow]:
        stmt = (
            select(NotificationRow)
            .where(
                NotificationRow.read == False,
                NotificationRow.recipient.in_([recipient, "all"]),
            )
            .order_by(NotificationRow.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_project(self, project_id: str, limit: int = 50) -> list[NotificationRow]:
        stmt = (
            select(NotificationRow)
            .where(NotificationRow.project_id == project_id)
            .order_by(NotificationRow.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_read(self, notification_id: str) -> bool:
        stmt = (
            update(NotificationRow)
            .where(NotificationRow.notification_id == notification_id)
            .values(read=True)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0
