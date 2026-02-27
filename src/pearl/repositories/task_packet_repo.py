"""TaskPacket repository."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.task_packet import TaskPacketRow
from pearl.repositories.base import BaseRepository


class TaskPacketRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, TaskPacketRow)

    async def get(self, task_packet_id: str) -> TaskPacketRow | None:
        return await self.get_by_id("task_packet_id", task_packet_id)

    async def list_by_project(self, project_id: str) -> list[TaskPacketRow]:
        stmt = select(TaskPacketRow).where(TaskPacketRow.project_id == project_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_open_for_rule(
        self, project_id: str, rule_id: str
    ) -> TaskPacketRow | None:
        """Find an open (uncompleted) task packet for a specific rule+project."""
        all_packets = await self.list_by_project(project_id)
        for p in all_packets:
            data = p.packet_data or {}
            if (
                data.get("rule_id") == rule_id
                and data.get("task_type") == "remediate_gate_blocker"
                and data.get("status") in ("pending", "in_progress")
                and p.completed_at is None
            ):
                return p
        return None
