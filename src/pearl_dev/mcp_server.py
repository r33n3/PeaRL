"""MCP stdio server for pearl-dev developer tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from pearl_dev.approval_terminal import ApprovalManager
from pearl_dev.audit import AuditLogger
from pearl_dev.context_loader import ContextLoader
from pearl_dev.mcp_tool_defs import TOOL_DEFINITIONS
from pearl_dev.policy_engine import PolicyEngine
from pearl_dev.task_packet_local import generate_task_packet_local


class PearlDevMCPServer:
    """MCP server that dispatches tool calls to pearl-dev components.

    Communicates via JSON-RPC 2.0 over stdin/stdout.
    """

    def __init__(
        self,
        package_path: Path,
        audit_path: Path,
        approvals_dir: Path,
    ) -> None:
        self._loader = ContextLoader(package_path)
        self._audit = AuditLogger(audit_path)
        self._approval = ApprovalManager(approvals_dir)
        self._engine: PolicyEngine | None = None
        self._last_mtime: float | None = None

    def _get_engine(self) -> PolicyEngine:
        """Get or reload the policy engine if the package file changed."""
        mtime = self._loader.path.stat().st_mtime if self._loader.path.exists() else None
        if self._engine is None or mtime != self._last_mtime:
            self._loader.invalidate()
            pkg = self._loader.load()
            self._engine = PolicyEngine(pkg)
            self._last_mtime = mtime
        return self._engine

    # ── Tool dispatch ────────────────────────────────────────────────────

    def handle_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Dispatch a single tool call and return the result."""
        # Tools that don't need the policy engine
        if tool_name == "pearl_check_promotion":
            return self._handle_check_promotion()
        elif tool_name == "pearl_register_repo":
            return self._handle_register_repo(arguments)
        elif tool_name == "pearl_request_approval":
            return self._handle_request_approval(arguments)
        elif tool_name == "pearl_report_evidence":
            return self._handle_report_evidence(arguments)
        elif tool_name == "pearl_get_governance_costs":
            return self._handle_get_governance_costs(arguments)

        # Tools that need the policy engine
        engine = self._get_engine()

        if tool_name == "pearl_get_task_context":
            return self._handle_get_task_context(engine, arguments)
        elif tool_name == "pearl_check_action":
            return self._handle_check_action(engine, arguments)
        elif tool_name == "pearl_check_diff":
            return self._handle_check_diff(engine, arguments)
        elif tool_name == "pearl_get_policy_summary":
            return self._handle_get_policy_summary(engine)
        else:
            return {"error": f"Unknown tool: {tool_name}"}

    def _handle_get_task_context(
        self, engine: PolicyEngine, args: dict[str, Any]
    ) -> dict[str, Any]:
        packet = generate_task_packet_local(
            package=engine.package,
            task_type=args["task_type"],
            task_summary=args["task_summary"],
            trace_id=f"mcp_{args.get('task_type', 'unknown')}",
            affected_components=args.get("affected_components"),
            change_hints=args.get("change_hints"),
        )
        self._audit.log(
            "task_context",
            args["task_type"],
            "generated",
            trace_id=packet.trace_id,
            tool_name="pearl_get_task_context",
        )
        return json.loads(packet.model_dump_json(exclude_none=True))

    def _handle_check_action(
        self, engine: PolicyEngine, args: dict[str, Any]
    ) -> dict[str, Any]:
        result = engine.check_action(args["action"])
        self._audit.log(
            "action_check",
            args["action"],
            result.decision,
            reason=result.reason,
            tool_name="pearl_check_action",
        )
        return {
            "decision": result.decision,
            "reason": result.reason,
            "policy_ref": result.policy_ref,
        }

    def _handle_check_diff(
        self, engine: PolicyEngine, args: dict[str, Any]
    ) -> dict[str, Any]:
        violations = engine.check_diff(args["diff_text"])
        self._audit.log(
            "diff_check",
            "check_diff",
            "violations_found" if violations else "clean",
            details={"violation_count": len(violations)},
            tool_name="pearl_check_diff",
        )
        return {
            "violations": [
                {
                    "pattern": v.pattern,
                    "description": v.description,
                    "line": v.line,
                    "snippet": v.snippet,
                }
                for v in violations
            ],
            "clean": len(violations) == 0,
        }

    def _handle_request_approval(self, args: dict[str, Any]) -> dict[str, Any]:
        request_data = self._approval.request_approval(
            action=args["action"],
            reason=args["reason"],
            context=args.get("context"),
        )
        self._audit.log(
            "approval_request",
            args["action"],
            "pending",
            reason=args["reason"],
            tool_name="pearl_request_approval",
            details={"approval_id": request_data["approval_id"]},
        )
        return {
            "approval_id": request_data["approval_id"],
            "status": "pending",
        }

    def _handle_report_evidence(self, args: dict[str, Any]) -> dict[str, Any]:
        self._audit.log(
            "evidence",
            args["evidence_type"],
            "logged",
            reason=args["summary"],
            tool_name="pearl_report_evidence",
            details=args.get("details", {}),
        )
        return {"logged": True}

    def _handle_get_policy_summary(self, engine: PolicyEngine) -> dict[str, Any]:
        summary = engine.get_policy_summary()
        self._audit.log(
            "policy_summary",
            "get_summary",
            "retrieved",
            tool_name="pearl_get_policy_summary",
        )
        return summary

    def _handle_register_repo(self, args: dict[str, Any]) -> dict[str, Any]:
        """Register the current repo as a scan target via the PeaRL API."""
        import subprocess

        from pearl_dev.api_client import PearlAPIClient
        from pearl_dev.config import find_project_root, load_config

        # Auto-detect project_id from config
        try:
            root = find_project_root(self._loader.path.parent.parent)
            config = load_config(root)
            project_id = config.project_id
            api_url = config.api_url
        except Exception:
            return {"error": "Could not load pearl-dev.toml config"}

        # Auto-detect repo URL
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return {"error": "Could not detect git remote URL"}
            repo_url = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return {"error": "Git not available or timed out"}

        # Auto-detect branch
        branch = args.get("branch")
        if not branch:
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    capture_output=True, text=True, timeout=10,
                )
                branch = result.stdout.strip() if result.returncode == 0 else "main"
            except (subprocess.TimeoutExpired, FileNotFoundError):
                branch = "main"

        tool_type = args.get("tool_type", "mass")
        scan_frequency = args.get("scan_frequency", "daily")

        client = PearlAPIClient(api_url)
        response = client.register_scan_target(
            project_id, repo_url,
            tool_type=tool_type, branch=branch, scan_frequency=scan_frequency,
        )

        if response:
            self._audit.log(
                "scan_target_registered",
                repo_url,
                "registered",
                tool_name="pearl_register_repo",
                details={"scan_target_id": response.get("scan_target_id"), "tool_type": tool_type},
            )
            return {
                "registered": True,
                "scan_target_id": response.get("scan_target_id"),
                "repo_url": repo_url,
                "branch": branch,
                "tool_type": tool_type,
                "scan_frequency": scan_frequency,
            }
        else:
            return {"error": "Failed to register scan target (may already exist or API unavailable)"}

    def _handle_get_governance_costs(self, args: dict[str, Any]) -> dict[str, Any]:
        """Get governance cost report from the cost ledger."""
        from pearl_dev.agent.cost_tracker import CostTracker

        # Derive project root from the package path
        project_root = self._loader.path.parent.parent
        tracker = CostTracker(project_root)
        summary = tracker.summary()

        fmt = args.get("format", "summary")
        if fmt == "json":
            return summary.to_dict()
        elif fmt == "detailed":
            entries = tracker.load_all()
            return {
                **summary.to_dict(),
                "entries": [e.to_dict() for e in entries],
            }
        else:
            return {
                "report": summary.format_report(),
                **summary.to_dict(),
            }

    def _handle_check_promotion(self) -> dict[str, Any]:
        """Check promotion readiness from locally cached evaluation."""
        readiness_path = self._loader.path.parent / "promotion-readiness.json"
        if not readiness_path.exists():
            return {
                "status": "not_evaluated",
                "message": "Run `pearl-dev sync` to fetch promotion readiness from the PeaRL API.",
            }

        data = json.loads(readiness_path.read_text(encoding="utf-8"))

        rule_results = data.get("rule_results", [])
        passing = [r for r in rule_results if r.get("result") == "passed"]
        blocking = [r for r in rule_results if r.get("result") not in ("passed", "skip")]

        return {
            "current_env": data.get("source_environment", data.get("current_environment", "?")),
            "next_env": data.get("target_environment", data.get("next_environment", "?")),
            "status": data.get("status", "unknown"),
            "progress_pct": data.get("progress_pct", 0),
            "passed_count": data.get("passed_count", 0),
            "total_count": data.get("total_count", 0),
            "passing": [{"rule_type": r.get("rule_type"), "message": r.get("message")} for r in passing],
            "blocking": [{"rule_type": r.get("rule_type"), "message": r.get("message")} for r in blocking],
            "next_steps": [f"Fix: {r.get('rule_type')} — {r.get('message')}" for r in blocking],
        }

    # ── JSON-RPC 2.0 stdio loop ─────────────────────────────────────────

    def get_tool_definitions(self) -> list[dict]:
        """Return MCP tool definitions for the initialize response."""
        return TOOL_DEFINITIONS

    def run_stdio(self) -> None:
        """Run the MCP server reading JSON-RPC from stdin, writing to stdout."""
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
                    "serverInfo": {"name": "pearl-dev", "version": "0.1.0"},
                })
            elif method == "tools/list":
                self._write_result(req_id, {
                    "tools": self.get_tool_definitions(),
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


if __name__ == "__main__":
    from pathlib import Path

    from pearl_dev.config import find_project_root, load_config

    directory = None
    if "--directory" in sys.argv:
        idx = sys.argv.index("--directory")
        if idx + 1 < len(sys.argv):
            directory = sys.argv[idx + 1]

    root = find_project_root(Path(directory) if directory else None)
    config = load_config(root)

    server = PearlDevMCPServer(
        package_path=root / config.package_path,
        audit_path=root / config.audit_path,
        approvals_dir=root / config.approvals_dir,
    )
    server.run_stdio()
