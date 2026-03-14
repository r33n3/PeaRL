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

import httpx

from pearl_dev.mcp_tool_defs import TOOL_DEFINITIONS as LOCAL_TOOL_DEFS

# Names of tools handled locally (no API needed)
LOCAL_TOOL_NAMES = {t["name"] for t in LOCAL_TOOL_DEFS}

# New developer-accessible app-spec tools handled directly by PearlUnifiedMCPServer
APP_SPEC_TOOL_NAMES = {"analyzeProjectForAppSpec", "registerAppSpec"}

# Tool definitions for app-spec tools
APP_SPEC_TOOL_DEFS = [
    {
        "name": "analyzeProjectForAppSpec",
        "description": (
            "Analyzes the current project and returns a draft ApplicationSpec plus a requirements "
            "checklist. Reads .pearl.yaml, .mcp.json, pyproject.toml, and existing PeaRL scan "
            "findings to populate the spec. Review the draft and fill in any 'missing' fields, "
            "then call registerAppSpec with the finalized spec to clear the APP_SPEC_DEFINED gate."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "registerAppSpec",
        "description": (
            "Registers a finalized ApplicationSpec with the PeaRL API. "
            "Pass the spec JSON (from analyzeProjectForAppSpec or hand-crafted). "
            "Returns success status and whether the APP_SPEC_DEFINED gate was cleared."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "spec": {
                    "type": "object",
                    "description": "The ApplicationSpec to register. Must include application.app_id, owner_team, business_criticality, external_exposure, ai_enabled, and architecture.components.",
                },
            },
            "required": ["spec"],
        },
    },
]

# Tools that require a reviewer/governance/admin role — excluded from the developer profile
REVIEWER_ONLY_TOOLS = {
    # Approval decisions — human reviewers only
    "decideApproval",

    # Policy writes — governance/admin only
    "upsertOrgBaseline",
    "upsertApplicationSpec",
    "upsertEnvironmentProfile",
    "applyRecommendedBaseline",

    # Project metadata changes — deliberate admin action only
    # createProject is allowed for developer profile: new projects land in sandbox
    # and cannot reach dev without human approval at the promotion gate.
    "updateProject",

    # External review ingestion — operator/admin only
    "ingestSecurityReview",
}

# Profiles control which API tools are visible to the MCP client
# developer: everything except governance write / approval decision tools
# reviewer:  adds decideApproval + policy write tools
# admin:     full access (all tools)
PROFILES = {
    "developer": {"exclude": REVIEWER_ONLY_TOOLS},
    "reviewer": {"exclude": set()},
    "admin": {"exclude": set()},
}


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
        api_key: str | None = None,
        profile: str = "developer",
    ) -> None:
        self._project_root = project_root
        self._project_id = project_id
        self._environment = environment
        self._api_url = api_url
        self._auth_token = auth_token
        self._api_key = api_key
        self._excluded_tools = PROFILES.get(profile, PROFILES["developer"])["exclude"]

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
                api_key=self._api_key,
            )
        return self._api_server

    def _all_tool_definitions(self) -> list[dict]:
        """Merge local + API tool definitions, filtered by profile."""
        tools = list(LOCAL_TOOL_DEFS)
        # App-spec discovery/registration tools are always available to developer profile
        tools.extend(APP_SPEC_TOOL_DEFS)

        try:
            api_server = self._get_api_server()
            api_tools = api_server.list_tools()
            # Avoid duplicates (local tools take priority); exclude profile-restricted tools
            api_names_to_add = (
                {t["name"] for t in api_tools}
                - LOCAL_TOOL_NAMES
                - APP_SPEC_TOOL_NAMES
                - self._excluded_tools
            )
            for t in api_tools:
                if t["name"] in api_names_to_add:
                    tools.append(t)
        except Exception:
            pass  # API unavailable — local tools only

        return tools

    def handle_tool_call(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Route to local handler or API proxy."""
        if tool_name in APP_SPEC_TOOL_NAMES:
            if tool_name == "analyzeProjectForAppSpec":
                return self._handle_analyze_project_for_app_spec()
            elif tool_name == "registerAppSpec":
                return self._handle_register_app_spec(arguments.get("spec", {}))
        elif tool_name in LOCAL_TOOL_NAMES:
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
        return {"error": f"Unknown tool: {tool_name}"}

    # ── App Spec tools ──────────────────────────────────────────────────

    def _handle_analyze_project_for_app_spec(self) -> dict[str, Any]:
        """Analyze the project and return a draft ApplicationSpec + requirements checklist."""
        root = self._project_root
        requirements: list[dict] = []
        notes: list[str] = []

        # --- Read .pearl.yaml ---
        pearl_yaml_path = root / ".pearl.yaml"
        pearl_meta: dict = {}
        if pearl_yaml_path.exists():
            try:
                import yaml  # type: ignore[import]
                with pearl_yaml_path.open() as f:
                    pearl_meta = yaml.safe_load(f) or {}
            except Exception as e:
                notes.append(f"Could not parse .pearl.yaml: {e}")

        project_id = pearl_meta.get("project_id") or self._project_id
        owner_team = pearl_meta.get("owner_team", "")
        business_criticality = pearl_meta.get("business_criticality", "moderate")
        external_exposure = pearl_meta.get("external_exposure", "internal_only")
        ai_enabled = pearl_meta.get("ai_enabled", True)

        # --- Read .mcp.json for MCP server components ---
        mcp_components: list[dict] = []
        mcp_json_path = root / ".mcp.json"
        if mcp_json_path.exists():
            try:
                with mcp_json_path.open() as f:
                    mcp_data = json.load(f)
                servers = mcp_data.get("mcpServers", {})
                for server_id in servers:
                    mcp_components.append({
                        "id": server_id,
                        "type": "mcp_server",
                        "criticality": "moderate",
                    })
                if mcp_components:
                    notes.append(f"Found {len(mcp_components)} MCP server(s) in .mcp.json.")
            except Exception as e:
                notes.append(f"Could not parse .mcp.json: {e}")

        # --- Detect AI libraries from pyproject.toml / requirements.txt ---
        ai_libs_found: list[str] = []
        ai_surface_components: list[dict] = []
        AI_LIB_PATTERNS = {
            "anthropic": "anthropic_api",
            "openai": "openai_api",
            "llama_cpp": "llama_cpp_local",
            "google-generativeai": "gemini_api",
            "groq": "groq_api",
            "ollama": "ollama_local",
        }
        for dep_file in ["pyproject.toml", "requirements.txt"]:
            dep_path = root / dep_file
            if dep_path.exists():
                try:
                    content = dep_path.read_text()
                    for lib, component_id in AI_LIB_PATTERNS.items():
                        if lib in content and component_id not in [c["id"] for c in ai_surface_components]:
                            ai_libs_found.append(lib)
                            ai_surface_components.append({
                                "id": component_id,
                                "type": "ai_service",
                                "criticality": "high",
                            })
                except Exception as e:
                    notes.append(f"Could not read {dep_file}: {e}")

        if ai_libs_found:
            notes.append(f"Detected AI libraries: {', '.join(ai_libs_found)}.")

        # --- Fetch findings from PeaRL API to enrich components ---
        api_components: list[dict] = []
        try:
            r = httpx.get(
                f"{self._api_url}/projects/{project_id}/findings",
                timeout=10.0,
            )
            if r.status_code == 200:
                findings = r.json() if isinstance(r.json(), list) else r.json().get("findings", [])
                for f_item in findings:
                    affected = (f_item.get("full_data") or {}).get("affected_components", [])
                    for comp in (affected if isinstance(affected, list) else []):
                        comp_id = comp if isinstance(comp, str) else comp.get("id", "")
                        if comp_id and comp_id not in [c["id"] for c in api_components]:
                            api_components.append({"id": comp_id, "type": "internal_service"})
                if api_components:
                    notes.append(f"Found {len(api_components)} component(s) from scan findings.")
        except Exception:
            pass  # API unavailable — skip

        # --- Merge all components (deduplicate by id) ---
        all_components: list[dict] = []
        seen_ids: set[str] = set()
        for comp in ai_surface_components + mcp_components + api_components:
            if comp["id"] not in seen_ids:
                all_components.append(comp)
                seen_ids.add(comp["id"])

        # --- Build draft spec ---
        draft_spec: dict[str, Any] = {
            "schema_version": "1.1",
            "application": {
                "app_id": project_id.removeprefix("proj_") if project_id else "",
                "owner_team": owner_team,
                "business_criticality": business_criticality,
                "external_exposure": external_exposure,
                "ai_enabled": ai_enabled,
            },
            "architecture": {
                "components": all_components,
            },
            "data": {
                "classifications": [],
            },
            "responsible_ai": {},
        }

        # --- Build requirements checklist ---
        app = draft_spec["application"]
        req_fields = [
            ("application.app_id", app.get("app_id")),
            ("application.owner_team", app.get("owner_team")),
            ("application.business_criticality", app.get("business_criticality")),
            ("application.external_exposure", app.get("external_exposure")),
            ("application.ai_enabled", app.get("ai_enabled")),
        ]
        for field, value in req_fields:
            status = "discovered" if value not in (None, "", []) else "missing"
            entry: dict = {"field": field, "status": status}
            if status == "discovered":
                entry["value"] = value
            else:
                entry["guidance"] = f"Required — provide a value for {field}"
            requirements.append(entry)

        requirements.append({
            "field": "architecture.components",
            "status": "discovered" if all_components else "missing",
            "value": all_components if all_components else [],
            "guidance": "Add components for each AI service, MCP server, data store, or API gateway." if not all_components else None,
        })
        requirements.append({
            "field": "data.classifications",
            "status": "optional",
            "guidance": "List data types handled (e.g. PII, model_outputs, telemetry). Improves gate accuracy.",
        })
        requirements.append({
            "field": "responsible_ai",
            "status": "optional",
            "guidance": "Describe RAI mitigations, model cards, bias evaluations in use.",
        })

        confidence = "high" if all_components and owner_team else "medium" if all_components else "low"

        return {
            "draft_spec": draft_spec,
            "requirements": [r for r in requirements if r.get("guidance") is not None or r.get("status") != "discovered"],
            "confidence": confidence,
            "notes": " ".join(notes) if notes else "No additional notes.",
        }

    def _handle_register_app_spec(self, spec: dict[str, Any]) -> dict[str, Any]:
        """Validate and POST the ApplicationSpec to the PeaRL API."""
        if not spec:
            return {"error": "No spec provided. Call analyzeProjectForAppSpec first to get a draft."}

        # Basic validation — required fields
        app = spec.get("application", {})
        missing: list[str] = []
        for field in ("app_id", "owner_team", "business_criticality", "external_exposure", "ai_enabled"):
            if not app.get(field) and app.get(field) is not False:
                missing.append(f"application.{field}")
        if not spec.get("architecture", {}).get("components"):
            missing.append("architecture.components")
        if missing:
            return {
                "error": f"Spec is missing required fields: {', '.join(missing)}. Fix and retry.",
                "missing_fields": missing,
            }

        project_id = pearl_meta_project_id = None
        # Try reading project_id from .pearl.yaml
        pearl_yaml = self._project_root / ".pearl.yaml"
        if pearl_yaml.exists():
            try:
                import yaml  # type: ignore[import]
                pearl_meta_project_id = (yaml.safe_load(pearl_yaml.read_text()) or {}).get("project_id")
            except Exception:
                pass
        project_id = pearl_meta_project_id or self._project_id

        if not project_id or project_id == "unknown":
            return {"error": "Cannot determine project_id. Ensure .pearl.yaml has project_id set."}

        try:
            r = httpx.post(
                f"{self._api_url}/projects/{project_id}/app-spec",
                json=spec,
                timeout=30.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                return {
                    "success": True,
                    "app_id": data.get("app_id") or app.get("app_id"),
                    "project_id": project_id,
                    "gate_cleared": "APP_SPEC_DEFINED",
                    "message": "App spec registered. Re-run evaluatePromotionReadiness to confirm gate passage.",
                }
            else:
                return {
                    "success": False,
                    "http_status": r.status_code,
                    "error": r.text[:500],
                }
        except httpx.HTTPError as e:
            return {
                "success": False,
                "error": f"HTTP error contacting PeaRL API at {self._api_url}: {e}",
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
    parser.add_argument(
        "--api-key",
        help="API key for PeaRL auth (alternative to --auth-token)",
    )
    parser.add_argument(
        "--profile",
        choices=["developer", "reviewer", "admin"],
        default="developer",
        help="Tool profile: developer (default) hides approval-decision and policy-write tools; reviewer/admin expose all",
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

    import os
    api_key = args.api_key or os.environ.get("PEARL_API_KEY")

    server = PearlUnifiedMCPServer(
        project_root=root,
        project_id=project_id,
        environment=environment,
        api_url=api_url,
        auth_token=args.auth_token,
        api_key=api_key,
        profile=args.profile,
    )
    server.run_stdio()


if __name__ == "__main__":
    main()
