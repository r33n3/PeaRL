"""Core orchestration engine — runs workflows via Claude Agent SDK."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any, Callable

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)

from pearl_dev.agent.config import AgentConfig


@dataclass
class WorkflowResult:
    """Collects events from a workflow run."""

    text_output: str = ""
    tools_called: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    success: bool = True
    total_cost_usd: float | None = None
    duration_ms: int | None = None
    num_turns: int = 0
    session_id: str | None = None


def _build_options(
    config: AgentConfig,
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    agents: dict[str, Any] | None = None,
    hooks: dict[str, list[Any]] | None = None,
) -> ClaudeAgentOptions:
    """Build ClaudeAgentOptions from AgentConfig."""
    return ClaudeAgentOptions(
        max_turns=config.max_turns,
        model=config.model,
        permission_mode=config.permission_mode,
        cwd=str(config.project_root),
        mcp_servers={"pearl": config.mcp_server_config()},
        allowed_tools=allowed_tools or [],
        system_prompt=system_prompt,
        agents=agents,
        hooks=hooks,
        setting_sources=["project"],
    )


async def run_workflow(
    config: AgentConfig,
    workflow_prompt: str,
    workflow_name: str = "custom",
    allowed_tools: list[str] | None = None,
    system_prompt: str | None = None,
    agents: dict[str, Any] | None = None,
    hooks: dict[str, list[Any]] | None = None,
    on_text: Callable[[str], None] | None = None,
    on_tool: Callable[[str, dict], None] | None = None,
) -> WorkflowResult:
    """Execute a workflow via Claude Agent SDK.

    Uses ClaudeSDKClient for hook support. Streams events and
    collects them into a WorkflowResult. Automatically records
    cost to .pearl/cost-ledger.jsonl for governance cost transparency.
    """
    options = _build_options(
        config,
        allowed_tools=allowed_tools,
        system_prompt=system_prompt,
        agents=agents,
        hooks=hooks,
    )

    result = WorkflowResult()

    # Clear CLAUDECODE env var so the SDK can launch Claude Code CLI
    # as a subprocess (otherwise it detects nesting and refuses to start)
    saved_claudecode = os.environ.pop("CLAUDECODE", None)
    try:
        result = await _execute_workflow(options, workflow_prompt, result, on_text, on_tool)
    finally:
        if saved_claudecode is not None:
            os.environ["CLAUDECODE"] = saved_claudecode

    # Record cost to ledger for governance transparency
    _record_cost(config, result, workflow_name)

    # Best-effort push to API for backup
    _push_cost_to_api(config, result, workflow_name)

    return result


def _record_cost(config: AgentConfig, result: WorkflowResult, workflow_name: str) -> None:
    """Persist workflow cost to .pearl/cost-ledger.jsonl."""
    from datetime import datetime, timezone

    from pearl_dev.agent.cost_tracker import CostEntry, CostTracker

    try:
        tracker = CostTracker(config.project_root)
        entry = CostEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            project_id=config.project_id,
            environment=config.environment,
            workflow=workflow_name,
            model=config.model,
            cost_usd=result.total_cost_usd or 0.0,
            duration_ms=result.duration_ms,
            num_turns=result.num_turns,
            tools_called=result.tools_called,
            tool_count=len(result.tools_called),
            success=result.success,
            session_id=result.session_id,
        )
        tracker.record(entry)
    except Exception:
        pass  # Don't fail the workflow over cost tracking


def _push_cost_to_api(config: AgentConfig, result: WorkflowResult, workflow_name: str) -> None:
    """Best-effort push of single cost entry to PeaRL API."""
    from datetime import datetime, timezone

    try:
        from pearl_dev.api_client import PearlAPIClient

        client = PearlAPIClient(config.api_url)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "environment": config.environment,
            "workflow": workflow_name,
            "model": config.model,
            "cost_usd": result.total_cost_usd or 0.0,
            "duration_ms": result.duration_ms,
            "num_turns": result.num_turns,
            "tools_called": result.tools_called,
            "tool_count": len(result.tools_called),
            "success": result.success,
            "session_id": result.session_id,
        }
        client.push_governance_costs(config.project_id, [entry])
    except Exception:
        pass  # Don't fail workflow over telemetry


async def _execute_workflow(
    options: ClaudeAgentOptions,
    workflow_prompt: str,
    result: WorkflowResult,
    on_text: Callable[[str], None] | None = None,
    on_tool: Callable[[str, dict], None] | None = None,
) -> WorkflowResult:
    """Inner execution — separated so env var cleanup happens in finally."""
    async with ClaudeSDKClient(options=options) as client:
        await client.query(workflow_prompt)

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        result.text_output += block.text
                        if on_text:
                            on_text(block.text)
                    elif isinstance(block, ToolUseBlock):
                        result.tools_called.append(block.name)
                        if on_tool:
                            on_tool(block.name, block.input)
                    elif isinstance(block, ToolResultBlock):
                        if block.is_error:
                            result.errors.append(
                                f"{block.tool_use_id}: {block.content}"
                            )

            elif isinstance(message, ResultMessage):
                result.success = not message.is_error
                result.total_cost_usd = message.total_cost_usd
                result.duration_ms = message.duration_ms
                result.num_turns = message.num_turns
                result.session_id = message.session_id

    return result
