"""Policy enforcement hooks — PreToolUse/PostToolUse for governance."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import HookContext, HookMatcher

from pearl_dev.agent.config import AgentConfig


def build_hooks(config: AgentConfig) -> dict[str, list[HookMatcher]]:
    """Build hook configuration for a PeaRL agent workflow.

    Returns a dict mapping HookEvent names to lists of HookMatchers.
    """
    audit_path = config.project_root / ".pearl" / "audit.jsonl"

    return {
        "PreToolUse": [
            # Protect .pearl folder from deletion/modification
            HookMatcher(
                matcher="Bash",
                hooks=[_make_pearl_folder_guard_bash()],
                timeout=5,
            ),
            HookMatcher(
                matcher="Write",
                hooks=[_make_pearl_folder_guard_write()],
                timeout=5,
            ),
            HookMatcher(
                matcher="Edit",
                hooks=[_make_pearl_folder_guard_write()],
                timeout=5,
            ),
            # Block promotion if gates aren't passing
            HookMatcher(
                matcher="mcp__pearl__requestPromotion",
                hooks=[_make_promotion_gate_check(config)],
                timeout=30,
            ),
            # Warn on production-affecting operations
            HookMatcher(
                matcher="mcp__pearl__updateProject",
                hooks=[_make_prod_guard(config)],
                timeout=10,
            ),
        ],
        "PostToolUse": [
            # Audit log every PeaRL MCP tool call
            HookMatcher(
                hooks=[_make_audit_logger(audit_path)],
                timeout=5,
            ),
        ],
    }


def _make_pearl_folder_guard_bash():
    """Create a PreToolUse hook that blocks Bash commands deleting .pearl/."""

    async def _hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        from pearl_dev.pearl_folder_guard import BLOCK_MESSAGE, is_pearl_destructive_bash

        tool_input = input_data.get("tool_input", {})
        command = tool_input.get("command", "")
        if is_pearl_destructive_bash(command):
            return {"decision": "block", "reason": BLOCK_MESSAGE}
        return {}

    return _hook


def _make_pearl_folder_guard_write():
    """Create a PreToolUse hook that blocks Write/Edit calls targeting .pearl/."""

    async def _hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        from pearl_dev.pearl_folder_guard import BLOCK_MESSAGE, is_pearl_write_target

        tool_input = input_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "") or tool_input.get("path", "")
        if file_path and is_pearl_write_target(file_path):
            return {"decision": "block", "reason": BLOCK_MESSAGE}
        return {}

    return _hook


def _make_promotion_gate_check(config: AgentConfig):
    """Create a PreToolUse hook that checks promotion readiness."""

    async def _hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        """Block requestPromotion if gates aren't passing.

        Reads the locally cached promotion-readiness.json to check
        whether gates are passing. If not, blocks with a message.
        """
        readiness_path = config.project_root / ".pearl" / "promotion-readiness.json"
        if readiness_path.exists():
            try:
                data = json.loads(readiness_path.read_text(encoding="utf-8"))
                status = data.get("status", "unknown")
                if status not in ("ready", "passed"):
                    passed = data.get("passed_count", 0)
                    total = data.get("total_count", 0)
                    return {
                        "decision": "block",
                        "reason": (
                            f"Promotion blocked: gates are {passed}/{total} passing "
                            f"(status: {status}). Run evaluatePromotionReadiness "
                            f"first, then fix blocking rules."
                        ),
                    }
            except (json.JSONDecodeError, OSError):
                pass

        # Allow — no cached data means we can't check locally
        return {}

    return _hook


def _make_prod_guard(config: AgentConfig):
    """Create a PreToolUse hook that warns on prod-affecting operations."""

    async def _hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        """Add a warning when modifying projects in production."""
        tool_input = input_data.get("tool_input", {})
        # Check if we're in a production environment
        if config.environment in ("prod", "production"):
            return {
                "systemMessage": (
                    "WARNING: You are modifying a project in the PRODUCTION "
                    "environment. Proceed with caution."
                ),
            }
        return {}

    return _hook


def _make_audit_logger(audit_path: Path):
    """Create a PostToolUse hook that logs all tool calls."""

    async def _hook(
        input_data: dict[str, Any],
        tool_use_id: str | None,
        context: HookContext,
    ) -> dict[str, Any]:
        """Append tool call to .pearl/audit.jsonl."""
        tool_name = input_data.get("tool_name", "unknown")

        # Only log PeaRL MCP tool calls
        if not tool_name.startswith("mcp__pearl__"):
            return {}

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": "agent_tool_call",
            "tool_name": tool_name,
            "action": tool_name.removeprefix("mcp__pearl__"),
            "decision": "executed",
            "source": "pearl_agent_sdk",
        }

        try:
            audit_path.parent.mkdir(parents=True, exist_ok=True)
            with open(audit_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # Don't fail the workflow over audit logging

        return {}

    return _hook
