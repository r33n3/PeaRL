"""Routes for agent definition registration and assessment."""
from __future__ import annotations
import hashlib
import logging
from typing import Any
import yaml
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from pearl.dependencies import get_db, require_role
from pearl.config import settings
from pearl.integrations.adapters import get_agent_platform_adapter
from pearl.repositories.agent_definition_repo import AgentDefinitionRepository
from pearl.services.agent_assessment import AgentAssessmentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/projects/{project_id}", tags=["Agent Definitions"])


class AgentDefinitionRequest(BaseModel):
    git_ref: str
    git_path: str
    platform: str                    # "claude" | "openai"
    platform_agent_id: str | None = None
    definition: str                  # raw YAML or JSON string
    environment: str = "dev"


def _extract_capabilities(data: dict) -> dict:
    """Extract key capabilities from parsed agent definition dict."""
    return {
        "tools": data.get("tools", []),
        "mcp_servers": data.get("mcp_servers", []),
        "model": data.get("model"),
        "callable_agents": data.get("callable_agents", []),
        "skills": data.get("skills", []),
        "system_prompt_hash": hashlib.sha256(
            str(data.get("system_prompt", "")).encode()
        ).hexdigest()[:16] if data.get("system_prompt") else None,
    }


@router.post("/agent-definitions", status_code=202)
async def create_agent_definition(
    project_id: str,
    body: AgentDefinitionRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_db),
    _user: Any = Depends(require_role("operator")),
) -> dict:
    try:
        definition_dict = yaml.safe_load(body.definition) or {}
    except Exception:
        definition_dict = {}

    capabilities = _extract_capabilities(definition_dict)

    repo = AgentDefinitionRepository(session)
    row = await repo.create(
        project_id=project_id,
        git_ref=body.git_ref,
        git_path=body.git_path,
        platform=body.platform,
        platform_agent_id=body.platform_agent_id,
        definition=definition_dict,
        capabilities=capabilities,
        environment=body.environment,
        version=body.git_ref,
    )
    await session.commit()

    # Pass session_factory from app.state so background task can open its own session
    session_factory = getattr(request.app.state, "db_session_factory", None)
    if session_factory is not None:
        background_tasks.add_task(
            _run_assessment_background,
            project_id=project_id,
            definition_id=row.agent_definition_id,
            platform=body.platform,
            definition_yaml=body.definition,
            session_factory=session_factory,
        )

    return {
        "definition_id": row.agent_definition_id,
        "status": row.status,
    }


async def _run_assessment_background(
    project_id: str,
    definition_id: str,
    platform: str,
    definition_yaml: str,
    session_factory,
) -> None:
    """Background task: launch MASS assessment session."""
    if not settings.mass_agent_id:
        logger.warning(
            "MASS_AGENT_ID not configured — skipping assessment for definition_id=%s",
            definition_id,
        )
        return

    api_key = (
        settings.anthropic_api_key if platform == "claude" else settings.openai_api_key
    )
    if not api_key:
        logger.warning(
            "No API key configured for platform=%s — skipping assessment definition_id=%s",
            platform, definition_id,
        )
        return

    adapter = get_agent_platform_adapter(platform, api_key=api_key)

    try:
        async with session_factory() as session:
            service = AgentAssessmentService(
                adapter=adapter,
                session=session,
                mass_agent_id=settings.mass_agent_id,
                mass_environment_id=settings.mass_environment_id or None,
            )
            await service.assess_definition(
                project_id=project_id,
                definition_id=definition_id,
                platform=platform,
                definition_yaml=definition_yaml,
            )
            await session.commit()
    except Exception:
        logger.exception(
            "assessment_background_failed definition_id=%s", definition_id
        )
