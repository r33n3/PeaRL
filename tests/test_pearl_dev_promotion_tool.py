"""Tests for pearl_check_promotion MCP tool."""

import json
from pathlib import Path

import pytest

SAMPLE_PACKAGE = {
    "schema_version": "1.1",
    "kind": "PearlCompiledContextPackage",
    "package_metadata": {
        "package_id": "pkg_promo_tool_test",
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
    },
    "project_identity": {
        "project_id": "proj_promo_tool",
        "app_id": "test-app",
        "environment": "dev",
        "delivery_stage": "prototype",
        "ai_enabled": True,
    },
    "autonomy_policy": {
        "mode": "supervised_autonomous",
        "allowed_actions": ["code_edit"],
        "blocked_actions": ["prod_deploy"],
    },
    "security_requirements": {
        "required_controls": ["authz_checks"],
    },
}


@pytest.fixture
def promo_tool_project(tmp_path):
    """Set up a pearl-dev project with MCP server ready."""
    pearl_dir = tmp_path / ".pearl"
    pearl_dir.mkdir()
    (pearl_dir / "approvals").mkdir()

    # Write package
    pkg_path = pearl_dir / "compiled-context-package.json"
    pkg_path.write_text(json.dumps(SAMPLE_PACKAGE), encoding="utf-8")

    # Write audit log (empty)
    (pearl_dir / "audit.jsonl").write_text("", encoding="utf-8")

    return tmp_path


def _make_server(project_dir):
    from pearl_dev.mcp_server import PearlDevMCPServer

    return PearlDevMCPServer(
        package_path=project_dir / ".pearl" / "compiled-context-package.json",
        audit_path=project_dir / ".pearl" / "audit.jsonl",
        approvals_dir=project_dir / ".pearl" / "approvals",
    )


def test_check_promotion_no_cache(promo_tool_project):
    """Returns helpful message when no promotion-readiness.json exists."""
    server = _make_server(promo_tool_project)
    result = server.handle_tool_call("pearl_check_promotion", {})
    assert result["status"] == "not_evaluated"
    assert "pearl-dev sync" in result["message"]


def test_check_promotion_reads_cache(promo_tool_project):
    """Reads promotion readiness from cached .pearl/promotion-readiness.json."""
    # Write cached readiness
    readiness = {
        "source_environment": "dev",
        "target_environment": "preprod",
        "status": "partial",
        "passed_count": 9,
        "failed_count": 4,
        "total_count": 13,
        "progress_pct": 69.2,
        "rule_results": [
            {"rule_type": "project_registered", "result": "passed", "message": "OK"},
            {"rule_type": "org_baseline_attached", "result": "passed", "message": "OK"},
            {"rule_type": "critical_findings_zero", "result": "fail", "message": "1 critical finding"},
            {"rule_type": "fairness_case_defined", "result": "skip", "message": "Not AI-enabled"},
        ],
    }
    readiness_path = promo_tool_project / ".pearl" / "promotion-readiness.json"
    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")

    server = _make_server(promo_tool_project)
    result = server.handle_tool_call("pearl_check_promotion", {})

    assert result["status"] == "partial"
    assert result["current_env"] == "dev"
    assert result["next_env"] == "preprod"
    assert result["progress_pct"] == 69.2
    assert result["passed_count"] == 9
    assert result["total_count"] == 13

    # Passing should contain the 2 passed rules
    assert len(result["passing"]) == 2
    assert result["passing"][0]["rule_type"] == "project_registered"

    # Blocking should contain only the fail (not skip)
    assert len(result["blocking"]) == 1
    assert result["blocking"][0]["rule_type"] == "critical_findings_zero"

    # Next steps generated from blocking
    assert len(result["next_steps"]) == 1
    assert "critical_findings_zero" in result["next_steps"][0]


def test_check_promotion_all_passing(promo_tool_project):
    """When all rules pass, blocking and next_steps are empty."""
    readiness = {
        "source_environment": "sandbox",
        "target_environment": "dev",
        "status": "passed",
        "passed_count": 5,
        "failed_count": 0,
        "total_count": 5,
        "progress_pct": 100.0,
        "rule_results": [
            {"rule_type": "project_registered", "result": "passed", "message": "OK"},
            {"rule_type": "org_baseline_attached", "result": "passed", "message": "OK"},
            {"rule_type": "app_spec_defined", "result": "passed", "message": "OK"},
            {"rule_type": "no_hardcoded_secrets", "result": "passed", "message": "OK"},
            {"rule_type": "unit_tests_exist", "result": "passed", "message": "OK"},
        ],
    }
    readiness_path = promo_tool_project / ".pearl" / "promotion-readiness.json"
    readiness_path.write_text(json.dumps(readiness), encoding="utf-8")

    server = _make_server(promo_tool_project)
    result = server.handle_tool_call("pearl_check_promotion", {})

    assert result["status"] == "passed"
    assert result["progress_pct"] == 100.0
    assert len(result["blocking"]) == 0
    assert len(result["next_steps"]) == 0
    assert len(result["passing"]) == 5
