"""Tests for MCP server tool definitions and routing."""

import pytest

from pearl.mcp.server import MCPServer
from pearl.mcp.tools import TOOL_DEFINITIONS


def test_tool_definitions_count():
    """All 50 API operations have tool definitions."""
    assert len(TOOL_DEFINITIONS) == 50


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
    assert len(tools) == 50


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
    }
    actual = {t["name"] for t in TOOL_DEFINITIONS}
    assert actual == expected
