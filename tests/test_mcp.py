"""Tests for MCP server tool definitions and routing."""

import pytest

from pearl.mcp.server import MCPServer
from pearl.mcp.tools import TOOL_DEFINITIONS


def test_tool_definitions_count():
    """All 51 API operations have tool definitions."""
    assert len(TOOL_DEFINITIONS) == 51


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
    assert len(tools) == 51


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
            await server.call_tool("listGuardrails", {})

    assert len(audit_calls) == 1
    assert audit_calls[0]["tool_name"] == "listGuardrails"
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
            await server.call_tool("getProject", {"project_id": "proj_test"})

    assert len(audit_calls) == 1
    assert audit_calls[0]["project_id"] == "proj_test"


def test_required_tool_names():
    """Check all expected tool names are present."""
    expected = {
        "pearl_register_project",
        "createProject",
        "getProject",
        "updateProject",
        "upsertOrgBaseline",
        "upsertApplicationSpec",
        "upsertEnvironmentProfile",
        "compileContext",
        "getCompiledPackage",
        "generateTaskPacket",
        "ingestFindings",
        "generateRemediationSpec",
        "createApprovalRequest",
        "decideApproval",
        "createException",
        "generateReport",
        "getJobStatus",
        # Promotion gates
        "evaluatePromotionReadiness",
        "getPromotionReadiness",
        "requestPromotion",
        "getPromotionHistory",
        # Project summary
        "getProjectSummary",
        # Fairness governance
        "createFairnessCase",
        "submitEvidence",
        "ingestMonitoringSignal",
        "submitContextReceipt",
        # Scan targets
        "registerScanTarget",
        "listScanTargets",
        "updateScanTarget",
        # AI security scanning
        "runScan",
        "getScanResults",
        "assessCompliance",
        "listGuardrails",
        "getGuardrail",
        "getRecommendedGuardrails",
        "getRecommendedBaseline",
        "applyRecommendedBaseline",
        "listPolicyTemplates",
        "getPolicyTemplate",
        "ingestSecurityReview",
        # Remediation execution bridge
        "claimTaskPacket",
        "completeTaskPacket",
        # Governance verification
        "confirmClaudeMd",
        # Fairness attestation signing
        "signFairnessAttestation",
        # SonarQube integration
        "triggerSonarPull",
        "getSonarStatus",
        "runSonarScan",
        # Report PDF export
        "exportReportPdf",
        # Agent allowance profiles
        "pearl_allowance_check",
        # MASS 2.0 AI security scan
        "pearl_trigger_mass_scan",
        # LiteLLM contract compliance
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
