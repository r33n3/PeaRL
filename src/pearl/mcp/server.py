"""MCP protocol adapter exposing PeaRL API operations as tools.

This is a thin adapter layer that translates MCP tool calls into
HTTP requests against the PeaRL REST API.
"""

import json
import logging
from typing import Any

import httpx

from .tools import TOOL_DEFINITIONS

logger = logging.getLogger(__name__)


class MCPServer:
    """Model Context Protocol server for PeaRL.

    Wraps the PeaRL REST API and exposes it as MCP tool calls.
    """

    def __init__(self, base_url: str = "http://localhost:8080/api/v1", auth_token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token

    def list_tools(self) -> list[dict]:
        """Return available tool definitions."""
        return TOOL_DEFINITIONS

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict:
        """Dispatch a tool call to the appropriate API endpoint."""
        handler = self._route(tool_name)
        if handler is None:
            return {"error": f"Unknown tool: {tool_name}"}
        try:
            return await handler(arguments)
        except Exception as exc:
            logger.error("MCP tool %s failed: %s", tool_name, exc)
            return {"error": str(exc)}

    def _route(self, tool_name: str):
        routes = {
            "createProject": self._create_project,
            "getProject": self._get_project,
            "updateProject": self._update_project,
            "upsertOrgBaseline": self._upsert_org_baseline,
            "upsertApplicationSpec": self._upsert_app_spec,
            "upsertEnvironmentProfile": self._upsert_env_profile,
            "compileContext": self._compile_context,
            "getCompiledPackage": self._get_compiled_package,
            "generateTaskPacket": self._generate_task_packet,
            "ingestFindings": self._ingest_findings,
            "generateRemediationSpec": self._generate_remediation_spec,
            "createApprovalRequest": self._create_approval_request,
            "decideApproval": self._decide_approval,
            "createException": self._create_exception,
            "generateReport": self._generate_report,
            "getJobStatus": self._get_job_status,
            # New: Promotion gates
            "evaluatePromotionReadiness": self._evaluate_promotion,
            "getPromotionReadiness": self._get_promotion_readiness,
            "requestPromotion": self._request_promotion,
            "getPromotionHistory": self._get_promotion_history,
            # New: Project summary
            "getProjectSummary": self._get_project_summary,
            # New: Fairness governance
            "createFairnessCase": self._create_fairness_case,
            "submitEvidence": self._submit_evidence,
            "ingestMonitoringSignal": self._ingest_monitoring_signal,
            "submitContextReceipt": self._submit_context_receipt,
            # New: Scan targets
            "registerScanTarget": self._register_scan_target,
            "listScanTargets": self._list_scan_targets,
            "updateScanTarget": self._update_scan_target,
            # New: AI security scanning
            "runScan": self._run_scan,
            "getScanResults": self._get_scan_results,
            "assessCompliance": self._assess_compliance,
            "listGuardrails": self._list_guardrails,
            "getGuardrail": self._get_guardrail,
            "getRecommendedGuardrails": self._get_recommended_guardrails,
            "getRecommendedBaseline": self._get_recommended_baseline,
            "applyRecommendedBaseline": self._apply_recommended_baseline,
            "listPolicyTemplates": self._list_policy_templates,
            "getPolicyTemplate": self._get_policy_template,
            "ingestSecurityReview": self._ingest_security_review,
        }
        return routes.get(tool_name)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    async def _request(self, method: str, path: str, body: dict | None = None, params: dict | None = None) -> dict:
        url = f"{self.base_url}{path}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            if method == "GET":
                resp = await client.get(url, headers=self._headers(), params=params)
            elif method == "POST":
                resp = await client.post(url, json=body, headers=self._headers())
            elif method == "PUT":
                resp = await client.put(url, json=body, headers=self._headers())
            else:
                return {"error": f"Unsupported method: {method}"}
            return resp.json()

    # --- Original tool handlers ---

    async def _create_project(self, args: dict) -> dict:
        return await self._request("POST", "/projects", args)

    async def _get_project(self, args: dict) -> dict:
        return await self._request("GET", f"/projects/{args['project_id']}")

    async def _update_project(self, args: dict) -> dict:
        pid = args.pop("project_id")
        return await self._request("PUT", f"/projects/{pid}", args)

    async def _upsert_org_baseline(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("POST", f"/projects/{pid}/org-baseline", args["baseline"])

    async def _upsert_app_spec(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("POST", f"/projects/{pid}/app-spec", args["spec"])

    async def _upsert_env_profile(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("POST", f"/projects/{pid}/environment-profile", args["profile"])

    async def _compile_context(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {
            "schema_version": "1.1",
            "project_id": pid,
            "compile_options": args.get("compile_options", {}),
            "trace_id": args.get("trace_id", "mcp_trace"),
        }
        return await self._request("POST", f"/projects/{pid}/compile-context", body)

    async def _get_compiled_package(self, args: dict) -> dict:
        return await self._request("GET", f"/projects/{args['project_id']}/compiled-package")

    async def _generate_task_packet(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {
            "schema_version": "1.1",
            "task_type": args["task_type"],
            "task_summary": args["task_summary"],
            "environment": args["environment"],
            "trace_id": args.get("trace_id", "mcp_trace"),
        }
        return await self._request("POST", f"/projects/{pid}/task-packets", body)

    async def _ingest_findings(self, args: dict) -> dict:
        body = dict(args)
        body.setdefault("schema_version", "1.1")
        return await self._request("POST", "/findings/ingest", body)

    async def _generate_remediation_spec(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {
            "finding_refs": args["finding_refs"],
            "environment": args["environment"],
            "trace_id": args.get("trace_id", "mcp_trace"),
        }
        return await self._request("POST", f"/projects/{pid}/remediation-specs/generate", body)

    async def _create_approval_request(self, args: dict) -> dict:
        return await self._request("POST", "/approvals/requests", args)

    async def _decide_approval(self, args: dict) -> dict:
        aid = args["approval_request_id"]
        body = {k: v for k, v in args.items() if k != "approval_request_id"}
        return await self._request("POST", f"/approvals/{aid}/decide", body)

    async def _create_exception(self, args: dict) -> dict:
        body = dict(args)
        body.setdefault("schema_version", "1.1")
        body.setdefault("requested_by", "mcp_agent")
        body.setdefault("status", "pending")
        body.setdefault("trace_id", "mcp_trace")
        return await self._request("POST", "/exceptions", body)

    async def _generate_report(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {
            "schema_version": "1.1",
            "report_type": args["report_type"],
            "format": args.get("format", "json"),
            "trace_id": args.get("trace_id", "mcp_trace"),
        }
        return await self._request("POST", f"/projects/{pid}/reports/generate", body)

    async def _get_job_status(self, args: dict) -> dict:
        return await self._request("GET", f"/jobs/{args['job_id']}")

    # --- New: Promotion gate handlers ---

    async def _evaluate_promotion(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("POST", f"/projects/{pid}/promotions/evaluate")

    async def _get_promotion_readiness(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("GET", f"/projects/{pid}/promotions/readiness")

    async def _request_promotion(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("POST", f"/projects/{pid}/promotions/request")

    async def _get_promotion_history(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("GET", f"/projects/{pid}/promotions/history")

    # --- New: Project summary handler ---

    async def _get_project_summary(self, args: dict) -> dict:
        pid = args["project_id"]
        fmt = args.get("format", "markdown")
        return await self._request("GET", f"/projects/{pid}/summary", params={"format": fmt})

    # --- New: Fairness governance handlers ---

    async def _create_fairness_case(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {k: v for k, v in args.items() if k != "project_id"}
        return await self._request("POST", f"/projects/{pid}/fairness-cases", body)

    async def _submit_evidence(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {k: v for k, v in args.items() if k != "project_id"}
        return await self._request("POST", f"/projects/{pid}/evidence", body)

    async def _ingest_monitoring_signal(self, args: dict) -> dict:
        return await self._request("POST", "/monitoring/signals", args)

    async def _submit_context_receipt(self, args: dict) -> dict:
        return await self._request("POST", "/context/receipts", args)

    # --- New: Scan target handlers ---

    async def _register_scan_target(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {k: v for k, v in args.items() if k != "project_id"}
        return await self._request("POST", f"/projects/{pid}/scan-targets", body)

    async def _list_scan_targets(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("GET", f"/projects/{pid}/scan-targets")

    async def _update_scan_target(self, args: dict) -> dict:
        pid = args["project_id"]
        stid = args["scan_target_id"]
        body = {k: v for k, v in args.items() if k not in ("project_id", "scan_target_id")}
        return await self._request("PUT", f"/projects/{pid}/scan-targets/{stid}", body)

    # --- New: AI security scanning handlers ---

    async def _run_scan(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {
            "target_path": args["target_path"],
            "analyzers": args.get("analyzers"),
            "environment": args.get("environment", "dev"),
        }
        return await self._request("POST", f"/projects/{pid}/scans", body)

    async def _get_scan_results(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("GET", f"/projects/{pid}/scans/latest")

    async def _assess_compliance(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("GET", f"/projects/{pid}/compliance-assessment")

    async def _list_guardrails(self, args: dict) -> dict:
        params = {}
        if "category" in args:
            params["category"] = args["category"]
        if "severity" in args:
            params["severity"] = args["severity"]
        return await self._request("GET", "/guardrails", params=params)

    async def _get_guardrail(self, args: dict) -> dict:
        gid = args["guardrail_id"]
        return await self._request("GET", f"/guardrails/{gid}")

    async def _get_recommended_guardrails(self, args: dict) -> dict:
        pid = args["project_id"]
        return await self._request("GET", f"/projects/{pid}/recommended-guardrails")

    async def _get_recommended_baseline(self, args: dict) -> dict:
        params = {
            "ai_enabled": str(args.get("ai_enabled", True)).lower(),
            "business_criticality": args.get("business_criticality", "moderate"),
        }
        return await self._request("GET", "/baselines/recommended", params=params)

    async def _apply_recommended_baseline(self, args: dict) -> dict:
        pid = args["project_id"]
        # Get project to determine AI-enabled and criticality
        project = await self._request("GET", f"/projects/{pid}")
        ai_enabled = project.get("ai_enabled", True)
        criticality = project.get("business_criticality", "moderate")

        # Get recommended baseline
        from pearl.scanning.baseline_package import get_recommended_baseline
        baseline = get_recommended_baseline(ai_enabled, criticality)

        # Apply it as org baseline
        return await self._request("POST", f"/projects/{pid}/org-baseline", baseline)

    async def _list_policy_templates(self, args: dict) -> dict:
        params = {}
        if "category" in args:
            params["category"] = args["category"]
        return await self._request("GET", "/policy-templates", params=params)

    async def _get_policy_template(self, args: dict) -> dict:
        tid = args["template_id"]
        return await self._request("GET", f"/policy-templates/{tid}")

    async def _ingest_security_review(self, args: dict) -> dict:
        pid = args["project_id"]
        body = {
            "markdown": args["markdown"],
            "environment": args.get("environment", "dev"),
        }
        return await self._request("POST", f"/projects/{pid}/scans/security-review", body)
