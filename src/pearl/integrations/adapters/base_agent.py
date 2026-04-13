"""Abstract base adapter for agent platforms (Claude Managed Agents, OpenAI Agents API)."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class AgentSessionResult:
    status: str           # "completed" | "failed" | "interrupted"
    output: str | None    # final text output from the session
    files: list[str]      # file IDs (Claude Files API) or attachment IDs
    cost_usd: float | None
    raw: dict             # full platform response for debugging


@dataclass
class AgentSessionEvent:
    type: str             # "message" | "tool_call" | "tool_result" | "status_change"
    content: str | None
    tool_name: str | None
    raw: dict


class BaseAgentPlatformAdapter(ABC):
    """Common interface for all agent platform adapters."""

    @abstractmethod
    async def create_session(
        self,
        agent_id: str,
        task: str,
        environment_id: str | None = None,
    ) -> str:
        """Create a session on the platform. Returns platform_session_id."""
        ...

    @abstractmethod
    async def get_result(self, session_id: str) -> AgentSessionResult:
        """Retrieve the final result of a completed session."""
        ...

    @abstractmethod
    async def stream_events(
        self, session_id: str
    ) -> AsyncIterator[AgentSessionEvent]:
        """Stream events from a running session."""
        ...

    @abstractmethod
    async def interrupt(self, session_id: str) -> None:
        """Request interruption of a running session."""
        ...
