"""MCP tool description safety tests.

Asserts that no PeaRL MCP tool description exposes internal implementation
details that reduce the cost of the L2→L3 attack chain (schema discovery
followed by targeted governance endpoint exploitation).

Flagged strings that must not appear in tool descriptions:
  - PEARL_LOCAL         — env var name exposing bypass mechanism
  - RequireReviewer     — internal dependency name
  - REVIEWER_ROLES      — internal constant name
  - /api/v1/            — internal route path pattern
  - localhost           — internal host reference

Descriptions should say *what* a tool does without exposing *how* the
enforcement mechanism is implemented.

Reference: docs/security_research/governance_hardening_plan_v2.md §3.3
"""

import pytest

from pearl.mcp.tools import TOOL_DEFINITIONS


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FLAGGED_STRINGS = [
    "PEARL_LOCAL",
    "RequireReviewer",
    "REVIEWER_ROLES",
    "/api/v1/",
    "localhost",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_description_text(tool: dict) -> str:
    """Return all human-readable text from a tool definition for inspection."""
    parts = [tool.get("description", "")]
    schema = tool.get("inputSchema", {})
    parts.append(schema.get("description", ""))
    for prop in schema.get("properties", {}).values():
        parts.append(prop.get("description", ""))
        # Nested object properties
        for nested_prop in prop.get("properties", {}).values():
            parts.append(nested_prop.get("description", ""))
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_tool_definitions_is_nonempty():
    """Sanity: TOOL_DEFINITIONS must contain at least one tool."""
    assert len(TOOL_DEFINITIONS) > 0


@pytest.mark.parametrize("flagged", FLAGGED_STRINGS)
def test_no_tool_description_contains_flagged_string(flagged: str):
    """No MCP tool description should contain the flagged implementation-detail string."""
    offenders = []
    for tool in TOOL_DEFINITIONS:
        text = _collect_description_text(tool)
        if flagged.lower() in text.lower():
            offenders.append(tool["name"])

    assert not offenders, (
        f"Flagged string {flagged!r} found in tool description(s): {offenders}. "
        f"Rewrite the description to omit internal implementation details. "
        f"Reference: governance_hardening_plan_v2.md §3.3"
    )


def test_all_tools_have_name_and_description():
    """Every tool must have a non-empty name and description."""
    missing = []
    for tool in TOOL_DEFINITIONS:
        name = tool.get("name", "").strip()
        desc = tool.get("description", "").strip()
        if not name or not desc:
            missing.append(tool.get("name", "<unnamed>"))
    assert not missing, f"Tools missing name or description: {missing}"


def test_decide_approval_description_warns_agents():
    """pearl_decide_approval description must explicitly warn agents they cannot call it.

    Design intent: by telling agents upfront that this tool requires reviewer role
    and will return 403, we prevent wasted attempts and make the governance boundary
    legible in the tool list itself.
    """
    tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "pearl_decide_approval"), None)
    assert tool is not None, "pearl_decide_approval tool definition not found"
    desc = tool.get("description", "")
    assert "reviewer" in desc.lower(), (
        "pearl_decide_approval description must warn agents it requires reviewer role"
    )
    assert "403" in desc, (
        "pearl_decide_approval description must mention the 403 response agents will get"
    )


def test_tool_count():
    """Tool count matches expected value — update if tools are added or removed."""
    # Update this value when tools are added or removed.
    # This is a regression guard, not a strict limit.
    assert len(TOOL_DEFINITIONS) == 55, (
        f"Expected 55 tool definitions, got {len(TOOL_DEFINITIONS)}. "
        f"If you added or removed tools, update this test AND verify no new descriptions "
        f"contain flagged strings (run test_no_tool_description_contains_flagged_string)."
    )
