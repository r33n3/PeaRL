"""MCP stdio server wrapping the PeaRL API for Claude Desktop.

Reads JSON-RPC 2.0 messages from stdin, dispatches to the existing
MCPServer (which calls the PeaRL REST API via httpx), and writes
responses to stdout.

Usage:
    python -m pearl.mcp.stdio_server --api-url http://localhost:8080/api/v1
"""

import asyncio
import json
import sys
from typing import Any

from pearl.mcp.server import MCPServer


class PearlAPIMCPStdioServer:
    """JSON-RPC 2.0 stdio transport for the PeaRL API MCP server."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080/api/v1",
        auth_token: str | None = None,
    ) -> None:
        self._mcp = MCPServer(base_url=base_url, auth_token=auth_token)

    def run_stdio(self) -> None:
        """Read JSON-RPC from stdin line-by-line, write responses to stdout."""
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
                self._write_result(req_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "pearl-api", "version": "1.1.0"},
                })
            elif method == "tools/list":
                self._write_result(req_id, {
                    "tools": self._mcp.list_tools(),
                })
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                try:
                    result = asyncio.run(self._mcp.call_tool(tool_name, arguments))
                    self._write_result(req_id, {
                        "content": [{"type": "text", "text": json.dumps(result)}],
                    })
                except Exception as exc:
                    self._write_result(req_id, {
                        "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                        "isError": True,
                    })
            elif method == "notifications/initialized":
                pass  # Client notification, no response needed
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
        prog="pearl-api-mcp",
        description="PeaRL API MCP stdio server for Claude Desktop",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8080/api/v1",
        help="PeaRL API base URL (default: http://localhost:8080/api/v1)",
    )
    parser.add_argument("--auth-token", default=None, help="Bearer token for API auth")
    args = parser.parse_args()

    server = PearlAPIMCPStdioServer(base_url=args.api_url, auth_token=args.auth_token)
    server.run_stdio()


if __name__ == "__main__":
    main()
