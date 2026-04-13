"""Adapter for Anthropic Claude Managed Agents platform."""
from __future__ import annotations
import logging
from typing import AsyncIterator

try:
    import anthropic
except ImportError:
    anthropic = None  # type: ignore[assignment]

from pearl.integrations.adapters.base_agent import (
    AgentSessionEvent, AgentSessionResult, BaseAgentPlatformAdapter,
)

logger = logging.getLogger(__name__)

_COST_PER_INPUT_TOKEN = 3.0 / 1_000_000
_COST_PER_OUTPUT_TOKEN = 15.0 / 1_000_000


class ClaudeManagedAgentsAdapter(BaseAgentPlatformAdapter):
    """Wraps Anthropic beta sessions API for Claude Managed Agents."""

    def __init__(self, api_key: str) -> None:
        if anthropic is None:
            raise ImportError("anthropic package required: pip install anthropic")
        self._client = anthropic.AsyncAnthropic(api_key=api_key)

    async def create_session(self, agent_id: str, task: str, environment_id: str | None = None) -> str:
        kwargs: dict = {"agent": agent_id, "input": task}
        if environment_id:
            kwargs["environment"] = environment_id
        session = await self._client.beta.sessions.create(**kwargs)
        logger.info("claude_session_created agent_id=%s session_id=%s", agent_id, session.id)
        return session.id

    async def get_result(self, session_id: str) -> AgentSessionResult:
        session = await self._client.beta.sessions.retrieve(session_id)
        output_text: str | None = None
        files: list[str] = []
        for block in getattr(session, "output", []) or []:
            if getattr(block, "type", None) == "text":
                output_text = block.text.value
            elif getattr(block, "type", None) == "file":
                files.append(block.file.file_id)
        cost_usd: float | None = None
        usage = getattr(session, "usage", None)
        if usage:
            cost_usd = (
                getattr(usage, "input_tokens", 0) * _COST_PER_INPUT_TOKEN
                + getattr(usage, "output_tokens", 0) * _COST_PER_OUTPUT_TOKEN
            )
        return AgentSessionResult(
            status=session.status,
            output=output_text,
            files=files,
            cost_usd=cost_usd,
            raw=session.model_dump() if hasattr(session, "model_dump") else {},
        )

    async def stream_events(self, session_id: str) -> AsyncIterator[AgentSessionEvent]:
        async with self._client.beta.sessions.threads.stream(session_id) as stream:
            async for event in stream:
                event_type = getattr(event, "type", "unknown")
                content: str | None = None
                tool_name: str | None = None
                if event_type in ("content_block_delta", "message_delta"):
                    delta = getattr(event, "delta", None)
                    if delta:
                        content = getattr(delta, "text", None) or getattr(delta, "value", None)
                elif event_type == "tool_use":
                    tool_name = getattr(event, "name", None)
                    content = str(getattr(event, "input", ""))
                yield AgentSessionEvent(
                    type=event_type,
                    content=content,
                    tool_name=tool_name,
                    raw=event.model_dump() if hasattr(event, "model_dump") else {},
                )

    async def interrupt(self, session_id: str) -> None:
        await self._client.beta.sessions.interrupt(session_id)
        logger.info("claude_session_interrupted session_id=%s", session_id)
