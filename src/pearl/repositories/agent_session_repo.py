"""Repository for agent_sessions table."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.agent_session import AgentSessionRow
from pearl.services.id_generator import generate_id


class AgentSessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        definition_id: str,
        project_id: str,
        platform: str,
        platform_session_id: str,
        purpose: str,
    ) -> AgentSessionRow:
        row = AgentSessionRow(
            agent_session_id=generate_id("ses_"),
            definition_id=definition_id,
            project_id=project_id,
            platform=platform,
            platform_session_id=platform_session_id,
            purpose=purpose,
            status="running",
            started_at=datetime.now(timezone.utc),
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def get(self, session_id: str) -> AgentSessionRow | None:
        result = await self._session.execute(
            select(AgentSessionRow).where(
                AgentSessionRow.agent_session_id == session_id
            )
        )
        return result.scalar_one_or_none()

    async def update_result(
        self,
        session_id: str,
        status: str,
        result: dict | None = None,
        cost_usd: float | None = None,
    ) -> AgentSessionRow:
        row = await self.get(session_id)
        if row is None:
            raise ValueError(f"AgentSessionRow not found: {session_id}")
        row.status = status
        if result is not None:
            row.result = result
        if cost_usd is not None:
            row.cost_usd = cost_usd
        if status in ("completed", "failed", "interrupted"):
            row.completed_at = datetime.now(timezone.utc)
        await self._session.flush()
        return row
