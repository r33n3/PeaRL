"""Repository for agent_definitions table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.agent_definition import AgentDefinitionRow
from pearl.services.id_generator import generate_id


class AgentDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        project_id: str,
        git_ref: str,
        git_path: str,
        platform: str,
        platform_agent_id: str | None,
        definition: dict,
        capabilities: dict,
        environment: str,
        version: str,
    ) -> AgentDefinitionRow:
        row = AgentDefinitionRow(
            agent_definition_id=generate_id("def_"),
            project_id=project_id,
            git_ref=git_ref,
            git_path=git_path,
            platform=platform,
            platform_agent_id=platform_agent_id,
            definition=definition,
            capabilities=capabilities,
            environment=environment,
            status="pending_assessment",
            version=version,
            created_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, definition_id: str) -> AgentDefinitionRow | None:
        result = await self._session.execute(
            select(AgentDefinitionRow).where(
                AgentDefinitionRow.agent_definition_id == definition_id
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_for_project(
        self, project_id: str, environment: str
    ) -> AgentDefinitionRow | None:
        result = await self._session.execute(
            select(AgentDefinitionRow)
            .where(
                AgentDefinitionRow.project_id == project_id,
                AgentDefinitionRow.environment == environment,
            )
            .order_by(AgentDefinitionRow.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, definition_id: str, status: str
    ) -> AgentDefinitionRow:
        row = await self.get(definition_id)
        if row is None:
            raise ValueError(f"AgentDefinitionRow not found: {definition_id}")
        row.status = status
        await self._session.flush()
        return row
