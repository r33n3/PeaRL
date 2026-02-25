"""Tests for CLAUDE.md governance section injection."""

from pearl_dev.template_renderer import inject_governance_into_claude_md


SAMPLE_SECTION = """<!-- PEARL:GOVERNANCE:BEGIN -->
## PeaRL Governance — proj_test | dev | supervised_autonomous

- Call `pearl_check_action` before risky operations
- Full governance policy: `.pearl/GOVERNANCE.md`
<!-- PEARL:GOVERNANCE:END -->"""


class TestInjectGovernanceIntoCLAUDEMD:
    def test_inject_into_empty_file(self):
        result = inject_governance_into_claude_md("", SAMPLE_SECTION)
        assert "PEARL:GOVERNANCE:BEGIN" in result
        assert "PEARL:GOVERNANCE:END" in result
        assert "proj_test" in result

    def test_inject_preserves_developer_content(self):
        existing = "# My Project\n\nThis is my custom CLAUDE.md content.\n\n## Build\n\nRun tests."
        result = inject_governance_into_claude_md(existing, SAMPLE_SECTION)

        # Developer content preserved
        assert "My Project" in result
        assert "Run tests" in result
        # Governance injected
        assert "PEARL:GOVERNANCE:BEGIN" in result
        assert "proj_test" in result

    def test_reinject_updates_without_touching_developer_content(self):
        existing = (
            "# My Project\n\n"
            "<!-- PEARL:GOVERNANCE:BEGIN -->\n"
            "## OLD GOVERNANCE SECTION\n"
            "<!-- PEARL:GOVERNANCE:END -->\n\n"
            "## My Custom Section\n\nImportant stuff."
        )
        result = inject_governance_into_claude_md(existing, SAMPLE_SECTION)

        # Old governance replaced
        assert "OLD GOVERNANCE SECTION" not in result
        # New governance present
        assert "proj_test" in result
        # Developer content preserved
        assert "My Project" in result
        assert "Important stuff" in result
        assert "My Custom Section" in result

    def test_markers_correctly_placed(self):
        result = inject_governance_into_claude_md("", SAMPLE_SECTION)
        begin_idx = result.index("<!-- PEARL:GOVERNANCE:BEGIN -->")
        end_idx = result.index("<!-- PEARL:GOVERNANCE:END -->")
        assert begin_idx < end_idx

    def test_multiple_reinjects_are_idempotent(self):
        """Injecting multiple times only has one governance section."""
        content = "# My Project"
        result = inject_governance_into_claude_md(content, SAMPLE_SECTION)
        result = inject_governance_into_claude_md(result, SAMPLE_SECTION)
        result = inject_governance_into_claude_md(result, SAMPLE_SECTION)

        assert result.count("PEARL:GOVERNANCE:BEGIN") == 1
        assert result.count("PEARL:GOVERNANCE:END") == 1
        assert "My Project" in result
