"""AgentAssessmentService — launches MASS agent sessions to assess agent definitions."""
from __future__ import annotations
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from pearl.integrations.adapters.base_agent import BaseAgentPlatformAdapter
from pearl.repositories.agent_session_repo import AgentSessionRepository

logger = logging.getLogger(__name__)

_ASSESSMENT_TASK_TEMPLATE = """\
Assess the following agent definition for security, capability risks, and policy compliance.
Ingest your findings using the PeaRL MCP tools (pearl_ingest_finding, pearl_store_scanner_policy).
When complete, call pearl_complete_assessment with your verdict.

Agent definition:

{definition_yaml}
"""


class AgentAssessmentService:
    def __init__(
        self,
        adapter: BaseAgentPlatformAdapter,
        session: AsyncSession,
        mass_agent_id: str = "",
        mass_environment_id: str | None = None,
    ) -> None:
        self._adapter = adapter
        self._session = session
        self._mass_agent_id = mass_agent_id
        self._mass_environment_id = mass_environment_id

    async def assess_definition(
        self,
        project_id: str,
        definition_id: str,
        platform: str,
        definition_yaml: str,
    ) -> str:
        """Launch a MASS assessment session. Returns the platform_session_id.

        Findings arrive via MCP during the session — no polling needed for findings.
        AgentSessionRow.status is updated by the session status poller.
        """
        task = _ASSESSMENT_TASK_TEMPLATE.format(definition_yaml=definition_yaml)

        try:
            platform_session_id = await self._adapter.create_session(
                agent_id=self._mass_agent_id,
                task=task,
                environment_id=self._mass_environment_id,
            )
        except Exception:
            logger.exception(
                "assessment_session_failed definition_id=%s platform=%s",
                definition_id,
                platform,
            )
            raise
        logger.info(
            "assessment_session_created definition_id=%s platform=%s session_id=%s",
            definition_id, platform, platform_session_id,
        )

        session_repo = AgentSessionRepository(self._session)
        await session_repo.create(
            definition_id=definition_id,
            project_id=project_id,
            platform=platform,
            platform_session_id=platform_session_id,
            purpose="assessment",
        )

        return platform_session_id
