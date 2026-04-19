"""Project repository."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.project import ProjectRow
from pearl.repositories.base import BaseRepository


class ProjectRepository(BaseRepository):
    def __init__(self, session: AsyncSession):
        super().__init__(session, ProjectRow)

    async def get(self, project_id: str) -> ProjectRow | None:
        return await self.get_by_id("project_id", project_id)

    async def update_governance_fields(
        self,
        project_id: str,
        intake_card_id: str | None = None,
        goal_id: str | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        risk_classification: str | None = None,
        agent_members: dict | None = None,
        litellm_key_refs: list | None = None,
        memory_policy_refs: list | None = None,
        qualification_packet_id: str | None = None,
    ) -> ProjectRow:
        row = await self.get(project_id)
        if row is None:
            from pearl.errors.exceptions import NotFoundError
            raise NotFoundError("Project", project_id)
        if intake_card_id is not None:
            row.intake_card_id = intake_card_id
        if goal_id is not None:
            row.goal_id = goal_id
        if target_type is not None:
            row.target_type = target_type
        if target_id is not None:
            row.target_id = target_id
        if risk_classification is not None:
            row.risk_classification = risk_classification
        if agent_members is not None:
            row.agent_members = agent_members
        if litellm_key_refs is not None:
            row.litellm_key_refs = litellm_key_refs
        if memory_policy_refs is not None:
            row.memory_policy_refs = memory_policy_refs
        if qualification_packet_id is not None:
            row.qualification_packet_id = qualification_packet_id
        return row
