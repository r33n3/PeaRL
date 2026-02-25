"""Agent configuration — loads from pearl-dev.toml, builds SDK options."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentConfig:
    """Configuration for a PeaRL Agent SDK workflow run."""

    project_id: str
    environment: str
    project_root: Path
    api_url: str = "http://localhost:8080/api/v1"
    model: str = "claude-sonnet-4-20250514"
    permission_mode: str = "default"
    max_turns: int = 25
    verbose: bool = False

    @classmethod
    def from_pearl_dev(cls, project_root: Path | None = None, **overrides: Any) -> AgentConfig:
        """Build config from existing pearl-dev.toml."""
        from pearl_dev.config import find_project_root, load_config

        root = find_project_root(project_root)
        cfg = load_config(root)

        return cls(
            project_id=overrides.get("project_id", cfg.project_id),
            environment=overrides.get("environment", cfg.environment),
            project_root=root,
            api_url=overrides.get("api_url", cfg.api_url),
            model=overrides.get("model", "claude-sonnet-4-20250514"),
            permission_mode=overrides.get("permission_mode", "default"),
            max_turns=overrides.get("max_turns", 25),
            verbose=overrides.get("verbose", False),
        )

    @property
    def python_command(self) -> str:
        """Python executable for MCP server subprocess."""
        if os.name == "nt":
            return "python.exe"
        return sys.executable

    def mcp_server_config(self) -> dict[str, Any]:
        """MCP server config dict for ClaudeAgentOptions.mcp_servers."""
        return {
            "type": "stdio",
            "command": self.python_command,
            "args": [
                "-m", "pearl_dev.unified_mcp",
                "--directory", str(self.project_root).replace("\\", "/"),
            ],
            "env": {},
        }
