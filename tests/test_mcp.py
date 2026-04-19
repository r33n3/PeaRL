"""Tests for MCP server tool definitions and routing."""

import pytest

from pearl.mcp.server import MCPServer
from pearl.mcp.tools import TOOL_DEFINITIONS


def test_tool_definitions_count():
    """All 52 API operations have tool definitions."""
    assert len(TOOL_DEFINITIONS) == 52


def test_tool_definitions_structure():
    """Each tool has name, description, and inputSchema."""
    for tool in TOOL_DEFINITIONS:
        assert "name" in tool
        assert "description" in tool
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


def test_tool_names_are_unique():
    """No duplicate tool names."""
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert len(names) == len(set(names))


def test_mcp_server_list_tools():
    """MCPServer.list_tools returns all definitions."""
    server = MCPServer()
    tools = server.list_tools()
    assert len(tools) == 52


def test_mcp_server_routes_all_tools():
    """Every defined tool has a route handler."""
    server = MCPServer()
    for tool in TOOL_DEFINITIONS:
        handler = server._route(tool["name"])
        assert handler is not None, f"No handler for tool: {tool['name']}"


@pytest.mark.asyncio
async def test_mcp_server_unknown_tool():
    """Unknown tool returns error dict."""
    server = MCPServer()
    result = await server.call_tool("nonexistent_tool", {})
    assert "error" in result
    assert "Unknown tool" in result["error"]


@pytest.mark.asyncio
async def test_mcp_audit_called_without_project_id(client):
    """Tools without project_id in args must still call _write_mcp_audit with _global sentinel."""
    from unittest.mock import patch
    from pearl.mcp.server import MCPServer

    server = MCPServer(base_url="http://test", api_key="test-key")

    audit_calls = []

    async def capture_audit(tool_name, project_id, arguments):
        audit_calls.append({"tool_name": tool_name, "project_id": project_id})

    with patch.object(server, "_write_mcp_audit", side_effect=capture_audit):
        with patch.object(server, "_list_guardrails", return_value={"guardrails": []}):
            await server.call_tool("pearl_list_guardrails", {})

    assert len(audit_calls) == 1
    assert audit_calls[0]["tool_name"] == "pearl_list_guardrails"
    # project_id should be the _global sentinel (not None, not skipped)
    assert audit_calls[0]["project_id"] == "_global"


@pytest.mark.asyncio
async def test_mcp_audit_uses_project_id_when_present(client):
    """Tools with project_id in args must use that project_id in audit."""
    from unittest.mock import patch
    from pearl.mcp.server import MCPServer

    server = MCPServer(base_url="http://test", api_key="test-key")

    audit_calls = []

    async def capture_audit(tool_name, project_id, arguments):
        audit_calls.append({"tool_name": tool_name, "project_id": project_id})

    with patch.object(server, "_write_mcp_audit", side_effect=capture_audit):
        with patch.object(server, "_get_project", return_value={"project_id": "proj_test"}):
            await server.call_tool("pearl_get_project", {"project_id": "proj_test"})

    assert len(audit_calls) == 1
    assert audit_calls[0]["project_id"] == "proj_test"


def test_required_tool_names():
    """Check all expected tool names are present."""
    expected = {
        # Project management
        "pearl_register_project",
        "pearl_create_project",
        "pearl_get_project",
        "pearl_update_project",
        # Project configuration
        "pearl_set_org_baseline",
        "pearl_set_app_spec",
        "pearl_set_env_profile",
        # Context compilation
        "pearl_compile_context",
        "pearl_get_compiled_package",
        "pearl_generate_task_packet",
        # Findings
        "pearl_ingest_findings",
        "pearl_generate_remediation_spec",
        # Approvals & exceptions
        "pearl_request_approval",
        "pearl_decide_approval",
        "pearl_create_exception",
        # Reports
        "pearl_generate_report",
        "pearl_export_report_pdf",
        # Jobs
        "pearl_get_job_status",
        # Promotion gates
        "pearl_evaluate_promotion",
        "pearl_get_promotion_readiness",
        "pearl_request_promotion",
        "pearl_get_promotion_history",
        # Project summary
        "pearl_get_project_summary",
        # Fairness governance
        "pearl_create_fairness_case",
        "pearl_submit_evidence",
        "pearl_ingest_monitoring_signal",
        "pearl_submit_context_receipt",
        "pearl_sign_fairness_attestation",
        # Scan targets
        "pearl_register_scan_target",
        "pearl_list_scan_targets",
        "pearl_update_scan_target",
        # AI security scanning
        "pearl_run_scan",
        "pearl_get_scan_results",
        "pearl_assess_compliance",
        "pearl_list_guardrails",
        "pearl_get_guardrail",
        "pearl_get_recommended_guardrails",
        "pearl_get_recommended_baseline",
        "pearl_apply_recommended_baseline",
        "pearl_list_policy_templates",
        "pearl_get_policy_template",
        "pearl_ingest_security_review",
        # SonarQube
        "pearl_trigger_sonar_pull",
        "pearl_get_sonar_status",
        "pearl_run_sonar_scan",
        # Remediation bridge
        "pearl_claim_task_packet",
        "pearl_complete_task_packet",
        # Agent allowance profiles
        "pearl_allowance_check",
        # MASS 2.0
        "pearl_trigger_mass_scan",
        # Governance verification
        "pearl_confirm_claude_md",
        # LiteLLM contract compliance
        "pearl_submit_contract_snapshot",
        "pearl_check_agent_contract",
    }
    actual = {t["name"] for t in TOOL_DEFINITIONS}
    assert actual == expected


def test_check_agent_contract_tool_registered():
    """pearl_check_agent_contract is in TOOL_DEFINITIONS."""
    from pearl.mcp.tools import TOOL_DEFINITIONS
    names = [t["name"] for t in TOOL_DEFINITIONS]
    assert "pearl_check_agent_contract" in names


def test_check_agent_contract_tool_has_required_schema():
    """pearl_check_agent_contract schema declares packet_id as required."""
    from pearl.mcp.tools import TOOL_DEFINITIONS
    tool = next(t for t in TOOL_DEFINITIONS if t["name"] == "pearl_check_agent_contract")
    schema = tool["inputSchema"]
    assert "packet_id" in schema["properties"]
    assert "packet_id" in schema.get("required", [])
