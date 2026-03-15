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


def test_decide_approval_description_does_not_describe_role_requirement():
    """decideApproval description must not leak which roles can call it."""
    tool = next((t for t in TOOL_DEFINITIONS if t["name"] == "decideApproval"), None)
    assert tool is not None, "decideApproval tool definition not found"
    desc = tool.get("description", "")
    role_leaking_phrases = [
        "reviewer",
        "requires role",
        "admin role",
        "operator role",
    ]
    found = [p for p in role_leaking_phrases if p.lower() in desc.lower()]
    assert not found, (
        f"decideApproval description exposes role names: {found}. "
        f"Description should say what the tool does, not who is allowed to call it."
    )


def test_tool_count():
    """Tool count matches expected value — update if tools are added or removed."""
    # Update this value when tools are added or removed.
    # This is a regression guard, not a strict limit.
    assert len(TOOL_DEFINITIONS) == 41, (
        f"Expected 41 tool definitions, got {len(TOOL_DEFINITIONS)}. "
        f"If you added or removed tools, update this test AND verify no new descriptions "
        f"contain flagged strings (run test_no_tool_description_contains_flagged_string)."
    )
