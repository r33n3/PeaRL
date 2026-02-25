"""Tests for pearl-dev sync command and CLAUDE.md/GOVERNANCE.md rendering."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from pearl.models.compiled_context import CompiledContextPackage

# Minimal compiled context package for testing
SAMPLE_PACKAGE = {
    "schema_version": "1.1",
    "kind": "PearlCompiledContextPackage",
    "package_metadata": {
        "package_id": "pkg_test_sync123456",
        "compiled_from": {
            "org_baseline_id": "orgb_test",
            "app_spec_id": "test-app",
            "environment_profile_id": "envp_test",
        },
        "integrity": {
            "signed": False,
            "hash": "29a27a0d44aa32e7ec69c1c91b2ee9e5",
            "hash_alg": "sha256",
            "compiled_at": "2026-01-01T00:00:00Z",
        },
        "compiler_version": "1.1.0",
    },
    "project_identity": {
        "project_id": "proj_sync_test",
        "app_id": "test-app",
        "environment": "dev",
        "delivery_stage": "prototype",
        "ai_enabled": True,
    },
    "autonomy_policy": {
        "mode": "supervised_autonomous",
        "allowed_actions": ["code_edit", "test_run"],
        "blocked_actions": ["prod_deploy"],
        "approval_required_for": [],
    },
    "security_requirements": {
        "required_controls": ["authz_checks"],
        "prohibited_patterns": ["hardcoded_secrets"],
    },
}

SAMPLE_READINESS = {
    "evaluation_id": "eval_test123",
    "project_id": "proj_sync_test",
    "source_environment": "dev",
    "target_environment": "pilot",
    "status": "partial",
    "passed_count": 8,
    "failed_count": 5,
    "total_count": 13,
    "progress_pct": 61.5,
    "blockers": ["Missing security review", "Critical findings"],
    "rule_results": [
        {"rule_id": "rule_project_registered", "rule_type": "project_registered", "result": "passed", "message": "Project is registered"},
        {"rule_id": "rule_org_baseline_attached", "rule_type": "org_baseline_attached", "result": "passed", "message": "Org baseline attached"},
        {"rule_id": "rule_critical_findings_zero", "rule_type": "critical_findings_zero", "result": "fail", "message": "2 critical findings open"},
        {"rule_id": "rule_fairness_case_defined", "rule_type": "fairness_case_defined", "result": "fail", "message": "No fairness case defined"},
    ],
}

SAMPLE_SCAN_TARGETS = [
    {
        "scan_target_id": "scnt_test1",
        "project_id": "proj_sync_test",
        "repo_url": "https://github.com/org/repo",
        "branch": "main",
        "tool_type": "mass",
        "scan_frequency": "daily",
        "status": "active",
        "environment_scope": None,
        "labels": None,
        "last_scanned_at": None,
        "last_scan_status": None,
    },
]


@pytest.fixture
def sync_project(tmp_path):
    """Set up a minimal pearl-dev project structure for sync testing."""
    pearl_dir = tmp_path / ".pearl"
    pearl_dir.mkdir()

    # Write compiled context package
    pkg_path = pearl_dir / "compiled-context-package.json"
    pkg_path.write_text(json.dumps(SAMPLE_PACKAGE), encoding="utf-8")

    # Write pearl-dev.toml
    toml_content = """[pearl-dev]
project_id = "proj_sync_test"
package_path = ".pearl/compiled-context-package.json"
audit_path = ".pearl/audit.jsonl"
approvals_dir = ".pearl/approvals"
api_url = "http://localhost:8080/api/v1"
"""
    (pearl_dir / "pearl-dev.toml").write_text(toml_content, encoding="utf-8")

    # Create approvals dir
    (pearl_dir / "approvals").mkdir()

    return tmp_path


def _make_mock_client(package=None, readiness=None, scan_targets=None):
    """Create a mock API client with standard defaults."""
    mock_client = MagicMock()
    mock_client.get_compiled_package.return_value = package or SAMPLE_PACKAGE
    mock_client.get_promotion_readiness.return_value = readiness
    mock_client.get_scan_targets.return_value = scan_targets
    return mock_client


def test_sync_downloads_and_renders(sync_project):
    """Sync command downloads package + readiness and creates GOVERNANCE.md + CLAUDE.md."""
    from pearl_dev.cli import cmd_sync

    mock_client = _make_mock_client(readiness=SAMPLE_READINESS, scan_targets=SAMPLE_SCAN_TARGETS)

    with patch("pearl_dev.api_client.PearlAPIClient", return_value=mock_client):
        args = MagicMock()
        args.directory = str(sync_project)
        args.api_url = None
        cmd_sync(args)

    # CLAUDE.md should have slim governance section with markers
    claude_md = (sync_project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "proj_sync_test" in claude_md
    assert "PEARL:GOVERNANCE:BEGIN" in claude_md
    assert "PEARL:GOVERNANCE:END" in claude_md
    assert "dev" in claude_md
    assert "pilot" in claude_md

    # GOVERNANCE.md should have full details
    governance_md = (sync_project / ".pearl" / "GOVERNANCE.md").read_text(encoding="utf-8")
    assert "proj_sync_test" in governance_md
    assert "Promotion Readiness" in governance_md

    # promotion-readiness.json should be saved
    readiness_path = sync_project / ".pearl" / "promotion-readiness.json"
    assert readiness_path.exists()
    data = json.loads(readiness_path.read_text(encoding="utf-8"))
    assert data["progress_pct"] == 61.5

    # scan-targets.json should be saved
    scan_path = sync_project / ".pearl" / "scan-targets.json"
    assert scan_path.exists()


def test_sync_without_evaluation(sync_project):
    """Sync when API returns no evaluation renders without promotion section."""
    from pearl_dev.cli import cmd_sync

    mock_client = _make_mock_client(readiness=None, scan_targets=None)

    with patch("pearl_dev.api_client.PearlAPIClient", return_value=mock_client):
        args = MagicMock()
        args.directory = str(sync_project)
        args.api_url = None
        cmd_sync(args)

    claude_md = (sync_project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "proj_sync_test" in claude_md
    # Should NOT have promotion info
    assert "Promotion" not in claude_md


def test_sync_preserves_developer_content(sync_project):
    """Sync preserves existing developer content in CLAUDE.md."""
    # Write initial CLAUDE.md with developer content
    dev_content = "# My Project\n\nThis is my custom CLAUDE.md content.\n\n## Build Instructions\n\nRun `npm test` for tests."
    (sync_project / "CLAUDE.md").write_text(dev_content, encoding="utf-8")

    from pearl_dev.cli import cmd_sync

    mock_client = _make_mock_client(readiness=SAMPLE_READINESS, scan_targets=None)

    with patch("pearl_dev.api_client.PearlAPIClient", return_value=mock_client):
        args = MagicMock()
        args.directory = str(sync_project)
        args.api_url = None
        cmd_sync(args)

    claude_md = (sync_project / "CLAUDE.md").read_text(encoding="utf-8")
    # Developer content is preserved
    assert "My Project" in claude_md
    assert "npm test" in claude_md
    # Governance section is injected
    assert "PEARL:GOVERNANCE:BEGIN" in claude_md
    assert "proj_sync_test" in claude_md


def test_governance_md_has_all_sections(sync_project):
    """GOVERNANCE.md template renders all expected sections."""
    from pearl_dev.cli import cmd_sync

    # Add fairness requirements to the package
    pkg_with_fairness = {**SAMPLE_PACKAGE}
    pkg_with_fairness["fairness_requirements"] = {
        "frs_id": "frs_001",
        "requirements": [
            {"statement": "No demographic bias", "requirement_type": "prohibit", "status": "pending", "gate_mode": "block"},
        ],
    }

    # Write the package with fairness
    pkg_path = sync_project / ".pearl" / "compiled-context-package.json"
    pkg_path.write_text(json.dumps(pkg_with_fairness), encoding="utf-8")

    mock_client = _make_mock_client(package=pkg_with_fairness, readiness=SAMPLE_READINESS, scan_targets=SAMPLE_SCAN_TARGETS)

    with patch("pearl_dev.api_client.PearlAPIClient", return_value=mock_client):
        args = MagicMock()
        args.directory = str(sync_project)
        args.api_url = None
        cmd_sync(args)

    governance_md = (sync_project / ".pearl" / "GOVERNANCE.md").read_text(encoding="utf-8")

    # Check all sections present in GOVERNANCE.md
    assert "## 1. Policy Enforcement" in governance_md
    assert "## 2. Allowed Actions" in governance_md
    assert "## 3. Blocked Actions" in governance_md
    assert "## 5. Prohibited Patterns" in governance_md
    assert "## 6. Required Tests" in governance_md
    assert "## 8. Promotion Readiness" in governance_md
    assert "## 9. Fairness Requirements" in governance_md
    assert "## 10. Registered Scan Targets" in governance_md
    assert "pearl_check_promotion" in governance_md
    assert "evaluatePromotionReadiness" in governance_md


def test_promotion_blocking_rules_in_governance_md(sync_project):
    """Blocking rules are rendered with details in GOVERNANCE.md."""
    from pearl_dev.cli import cmd_sync

    mock_client = _make_mock_client(readiness=SAMPLE_READINESS, scan_targets=None)

    with patch("pearl_dev.api_client.PearlAPIClient", return_value=mock_client):
        args = MagicMock()
        args.directory = str(sync_project)
        args.api_url = None
        cmd_sync(args)

    governance_md = (sync_project / ".pearl" / "GOVERNANCE.md").read_text(encoding="utf-8")
    assert "Blocking Rules" in governance_md
    assert "critical_findings_zero" in governance_md
    assert "Passing Rules" in governance_md
    assert "project_registered" in governance_md

    # CLAUDE.md slim section should show top 3 blockers
    claude_md = (sync_project / "CLAUDE.md").read_text(encoding="utf-8")
    assert "critical_findings_zero" in claude_md
