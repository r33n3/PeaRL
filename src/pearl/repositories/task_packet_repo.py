"""TaskPacket repository."""

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.task_packet import TaskPacketRow
from pearl.repositories.base import BaseRepository


class TaskPacketRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, TaskPacketRow)

    async def get(self, task_packet_id: str) -> TaskPacketRow | None:
        return await self.get_by_id("task_packet_id", task_packet_id)
