"""Unified PeaRL MCP server — combines local policy tools + API tools.

Single server that developers interact with. Shows project + environment
in the server name so you always know your context.

Local tools (policy checks, audit, approvals) work offline.
API tools (projects, findings, scanning, compliance) need the PeaRL server.

Usage:
    python -m pearl_dev.unified_mcp --directory /path/to/project
    python -m pearl_dev.unified_mcp --api-url http://localhost:8080/api/v1
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from pearl_dev.mcp_tool_defs import TOOL_DEFINITIONS as LOCAL_TOOL_DEFS

# Names of tools handled locally (no API needed)
LOCAL_TOOL_NAMES = {t["name"] for t in LOCAL_TOOL_DEFS}


class PearlUnifiedMCPServer:
    """Unified MCP server combining local pearl-dev tools and PeaRL API tools.

    - Local tools: pearl_check_action, pearl_check_diff, pearl_get_task_context,
      pearl_get_policy_summary, pearl_check_promotion, pearl_request_approval,
      pearl_report_evidence, pearl_register_repo
    - API tools: createProject, getProject, runScan, assessCompliance, ... (39 tools)
    """

    def __init__(
        self,
        project_root: Path,
        project_id: str = "unknown",
        environment: str = "dev",
        api_url: str = "http://localhost:8080/api/v1",
        auth_token: str | None = None,
    ) -> None:
        self._project_root = project_root
        self._project_id = project_id
        self._environment = environment
        self._api_url = api_url
        self._auth_token = auth_token

        # Lazy-initialized components
        self._dev_server = None
        self._api_server = None

    def _get_dev_server(self):
        """Lazy-init the local policy server (needs .pearl/ files)."""
        if self._dev_server is None:
            from pearl_dev.mcp_server import PearlDevMCPServer

            pearl_dir = self._project_root / ".pearl"
            self._dev_server = PearlDevMCPServer(
                package_path=pearl_dir / "compiled-context-package.json",
                audit_path=pearl_dir / "audit.jsonl",
                approvals_dir=pearl_dir / "approvals",
            )
        return self._dev_server

    def _get_api_server(self):
        """Lazy-init the API proxy server."""
        if self._api_server is None:
            from pearl.mcp.server import MCPServer

            self._api_server = MCPServer(
                base_url=self._api_url,
                auth_token=self._auth_token,
            )
        return self._api_server

    def _all_tool_definitions(self) -> list[dict]:
        """Merge local + API tool definitions."""
        tools = list(LOCAL_TOOL_DEFS)

        try:
            api_server = self._get_api_server()
            api_tools = api_server.list_tools()
            # Avoid duplicates (local tools take priority)
            api_names_to_add = {t["name"] for t in api_tools} - LOCAL_TOOL_NAMES
            for t in api_tools:
                if t["name"] in api_names_to_add:
                    tools.append(t)
        except Exception:
            pass  # API unavailable — local tools only

        return tools

    def handle_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route to local handler or API proxy."""
        if tool_name in LOCAL_TOOL_NAMES:
            try:
                dev = self._get_dev_server()
                return dev.handle_tool_call(tool_name, arguments)
            except Exception as exc:
                return {"error": f"Local tool failed: {exc}"}
        else:
            # API tool — run async
            try:
                api = self._get_api_server()
                return asyncio.run(api.call_tool(tool_name, arguments))
            except Exception as exc:
                return {
                    "error": f"API tool failed: {exc}. Is the PeaRL server running at {self._api_url}?",
                }

    # ── JSON-RPC 2.0 stdio loop ─────────────────────────────────────────

    def run_stdio(self) -> None:
        """Read JSON-RPC from stdin, write responses to stdout."""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                self._write_error(None, -32700, "Parse error")
                continue

            method = request.get("method", "")
            req_id = request.get("id")

            if method == "initialize":
                server_name = f"pearl [{self._project_id}] ({self._environment})"
                self._write_result(req_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": server_name, "version": "1.1.0"},
                })
            elif method == "tools/list":
                self._write_result(req_id, {
                    "tools": self._all_tool_definitions(),
                })
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                try:
                    result = self.handle_tool_call(tool_name, arguments)
                    self._write_result(req_id, {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    })
                except Exception as exc:
                    self._write_result(req_id, {
                        "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                        "isError": True,
                    })
            elif method == "notifications/initialized":
                pass
            else:
                self._write_error(req_id, -32601, f"Method not found: {method}")

    def _write_result(self, req_id: Any, result: Any) -> None:
        response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    def _write_error(self, req_id: Any, code: int, message: str) -> None:
        response = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        prog="pearl-mcp",
        description="Unified PeaRL MCP server for Claude Code",
    )
    parser.add_argument(
        "-d", "--directory",
        help="Project directory (default: auto-discover from cwd)",
    )
    parser.add_argument(
        "--api-url",
        help="PeaRL API URL (overrides pearl-dev.toml)",
    )
    parser.add_argument(
        "--auth-token",
        help="Bearer token for API auth",
    )
    args = parser.parse_args()

    # Try to load config from .pearl/pearl-dev.toml
    project_id = "unknown"
    environment = "dev"
    api_url = args.api_url or "http://localhost:8080/api/v1"

    try:
        from pearl_dev.config import find_project_root, load_config

        root = find_project_root(Path(args.directory) if args.directory else None)
        config = load_config(root)
        project_id = config.project_id
        environment = config.environment
        if not args.api_url:
            api_url = config.api_url
    except (FileNotFoundError, Exception):
        # No .pearl/ config — use defaults (still serves API tools)
        root = Path(args.directory).resolve() if args.directory else Path.cwd().resolve()

    server = PearlUnifiedMCPServer(
        project_root=root,
        project_id=project_id,
        environment=environment,
        api_url=api_url,
        auth_token=args.auth_token,
    )
    server.run_stdio()


if __name__ == "__main__":
    main()
