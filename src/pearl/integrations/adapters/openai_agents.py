"""Adapter for OpenAI Agents API (threads/runs against workflow ID)."""
from __future__ import annotations
import logging
from typing import AsyncIterator

try:
    import openai
except ImportError:
    openai = None  # type: ignore[assignment]

from pearl.integrations.adapters.base_agent import (
    AgentSessionEvent, AgentSessionResult, BaseAgentPlatformAdapter,
)

logger = logging.getLogger(__name__)

_COST_PER_INPUT_TOKEN = 2.5 / 1_000_000
_COST_PER_OUTPUT_TOKEN = 10.0 / 1_000_000


class OpenAIAgentsAdapter(BaseAgentPlatformAdapter):
    """Wraps OpenAI Assistants/Agents API (beta threads + runs)."""

    def __init__(self, api_key: str) -> None:
        if openai is None:
            raise ImportError("openai package required: pip install openai")
        self._client = openai.AsyncOpenAI(api_key=api_key)

    async def create_session(self, agent_id: str, task: str, environment_id: str | None = None) -> str:
        """Creates a thread with the task as user message, then starts a run.
        Returns composite session_id: "<thread_id>:<run_id>"
        """
        thread = await self._client.beta.threads.create(
            messages=[{"role": "user", "content": task}]
        )
        run = await self._client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=agent_id,
        )
        composite_id = f"{thread.id}:{run.id}"
        logger.info("openai_run_created agent_id=%s composite_id=%s", agent_id, composite_id)
        return composite_id

    def _parse_id(self, session_id: str) -> tuple[str, str]:
        thread_id, run_id = session_id.split(":", 1)
        return thread_id, run_id

    async def get_result(self, session_id: str) -> AgentSessionResult:
        thread_id, run_id = self._parse_id(session_id)
        run = await self._client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)
        output_text: str | None = None
        messages = await self._client.beta.threads.messages.list(thread_id=thread_id)
        for msg in messages.data:
            if msg.role == "assistant":
                for block in msg.content:
                    if getattr(block, "type", None) == "text":
                        output_text = block.text.value
                break
        cost_usd: float | None = None
        usage = getattr(run, "usage", None)
        if usage:
            cost_usd = (
                getattr(usage, "prompt_tokens", 0) * _COST_PER_INPUT_TOKEN
                + getattr(usage, "completion_tokens", 0) * _COST_PER_OUTPUT_TOKEN
            )
        status_map = {"completed": "completed", "failed": "failed", "cancelled": "interrupted", "expired": "failed"}
        status = status_map.get(run.status, run.status)
        return AgentSessionResult(
            status=status,
            output=output_text,
            files=[],
            cost_usd=cost_usd,
            raw=run.model_dump() if hasattr(run, "model_dump") else {},
        )

    async def stream_events(self, session_id: str) -> AsyncIterator[AgentSessionEvent]:
        thread_id, run_id = self._parse_id(session_id)
        async with self._client.beta.threads.runs.stream(thread_id=thread_id, run_id=run_id) as stream:
            async for event in stream:
                event_type = getattr(event, "event", "unknown")
                content: str | None = None
                tool_name: str | None = None
                data = getattr(event, "data", None)
                if event_type == "thread.message.delta" and data:
                    for block in getattr(getattr(data, "delta", None), "content", []) or []:
                        if getattr(block, "type", None) == "text":
                            content = getattr(block.text, "value", None)
                elif event_type == "thread.run.step.delta" and data:
                    step_delta = getattr(data, "delta", None)
                    step_details = getattr(step_delta, "step_details", None) if step_delta else None
                    if step_details and getattr(step_details, "type", None) == "tool_calls":
                        for tc in getattr(step_details, "tool_calls", []) or []:
                            tool_name = getattr(getattr(tc, "function", None), "name", None)
                yield AgentSessionEvent(
                    type=event_type,
                    content=content,
                    tool_name=tool_name,
                    raw=event.model_dump() if hasattr(event, "model_dump") else {},
                )

    async def interrupt(self, session_id: str) -> None:
        thread_id, run_id = self._parse_id(session_id)
        await self._client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run_id)
        logger.info("openai_run_cancelled thread_id=%s run_id=%s", thread_id, run_id)
