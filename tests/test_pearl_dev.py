"""Tests for pearl-dev developer-side policy enforcement layer.

Uses the aDiOS compiled context package as the reference fixture.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pearl.models.compiled_context import CompiledContextPackage

# ── Fixture: aDiOS compiled context ────────────────────────────────────────

ADIOS_PACKAGE_PATH = Path("C:/Users/bradj/Development/aDiOS/.pearl/compiled-context-package.json")

SAMPLE_PACKAGE = {
    "schema_version": "1.1",
    "kind": "PearlCompiledContextPackage",
    "package_metadata": {
        "package_id": "pkg_test1234567890ab",
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
        "project_id": "proj_test",
        "app_id": "test-app",
        "environment": "dev",
        "delivery_stage": "prototype",
        "ai_enabled": True,
    },
    "autonomy_policy": {
        "mode": "supervised_autonomous",
        "allowed_actions": ["code_edit", "test_run", "file_read", "file_write"],
        "blocked_actions": ["prod_deploy", "credential_rotation"],
        "approval_required_for": ["auth_flow_changes"],
    },
    "security_requirements": {
        "required_controls": ["authz_checks", "input_validation", "audit_logging"],
        "prohibited_patterns": ["hardcoded_secrets", "wildcard_iam_permissions"],
    },
    "responsible_ai_requirements": {
        "transparency": {
            "model_provenance_logging_required": True,
        },
    },
    "network_requirements": {
        "outbound_allowlist": ["llm-gateway.internal"],
        "public_egress_forbidden": True,
    },
    "required_tests": {
        "security": ["authz_negative_tests"],
        "rai": ["ai_disclosure_presence_test"],
        "functional": ["smoke_test"],
    },
    "approval_checkpoints": [
        {
            "checkpoint_id": "cp_auth",
            "trigger": "auth_flow_change",
            "required_roles": ["security_review"],
            "environment": "dev",
        }
    ],
    "evidence_requirements": ["decision_trace", "test_results"],
    "change_reassessment_triggers": {
        "architecture_delta": ["new_external_integration"],
    },
}


@pytest.fixture
def sample_package_data():
    return SAMPLE_PACKAGE.copy()


@pytest.fixture
def sample_package():
    return CompiledContextPackage.model_validate(SAMPLE_PACKAGE)


@pytest.fixture
def tmp_pearl_dir(tmp_path):
    """Create a temporary .pearl directory with a valid package."""
    pearl_dir = tmp_path / ".pearl"
    pearl_dir.mkdir()

    # Compute correct integrity hash for the test package
    import hashlib
    check_data = {"project_id": "proj_test", "package_id": "pkg_test1234567890ab"}
    canonical = json.dumps(check_data, sort_keys=True, separators=(",", ":"))
    correct_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    pkg_data = SAMPLE_PACKAGE.copy()
    pkg_data["package_metadata"] = {
        **pkg_data["package_metadata"],
        "integrity": {
            "signed": False,
            "hash": correct_hash,
            "hash_alg": "sha256",
            "compiled_at": "2026-01-01T00:00:00Z",
        },
    }

    pkg_path = pearl_dir / "compiled-context-package.json"
    pkg_path.write_text(json.dumps(pkg_data, indent=2), encoding="utf-8")
    return tmp_path


# ═══════════════════════════════════════════════════════════════════════════
# Step 13: Config
# ═══════════════════════════════════════════════════════════════════════════

class TestConfig:
    def test_load_config(self, tmp_pearl_dir):
        from pearl_dev.config import PearlDevConfig, load_config

        toml_path = tmp_pearl_dir / ".pearl" / "pearl-dev.toml"
        toml_path.write_text(
            '[pearl-dev]\nproject_id = "proj_test"\n', encoding="utf-8"
        )
        config = load_config(tmp_pearl_dir)
        assert config.project_id == "proj_test"
        assert config.package_path == ".pearl/compiled-context-package.json"

    def test_find_project_root(self, tmp_pearl_dir):
        from pearl_dev.config import find_project_root

        # Create a subdirectory
        sub = tmp_pearl_dir / "src" / "app"
        sub.mkdir(parents=True)
        root = find_project_root(sub)
        assert root == tmp_pearl_dir

    def test_missing_config_error(self, tmp_path):
        from pearl_dev.config import find_project_root

        with pytest.raises(FileNotFoundError, match="No .pearl/ directory"):
            find_project_root(tmp_path)


# ═══════════════════════════════════════════════════════════════════════════
# Step 14: Context Loader
# ═══════════════════════════════════════════════════════════════════════════

class TestContextLoader:
    def test_load_valid_package(self, tmp_pearl_dir):
        from pearl_dev.context_loader import ContextLoader

        pkg_path = tmp_pearl_dir / ".pearl" / "compiled-context-package.json"
        loader = ContextLoader(pkg_path)
        package = loader.load()
        assert package.project_identity.project_id == "proj_test"
        assert package.kind == "PearlCompiledContextPackage"

    def test_reject_tampered_hash(self, tmp_pearl_dir):
        from pearl_dev.context_loader import ContextLoader, IntegrityError

        pkg_path = tmp_pearl_dir / ".pearl" / "compiled-context-package.json"
        data = json.loads(pkg_path.read_text())
        data["package_metadata"]["integrity"]["hash"] = "0000000000000000deadbeef00000000"
        pkg_path.write_text(json.dumps(data), encoding="utf-8")

        loader = ContextLoader(pkg_path)
        with pytest.raises(IntegrityError, match="Hash mismatch"):
            loader.load()

    def test_cache_hit_on_same_mtime(self, tmp_pearl_dir):
        from pearl_dev.context_loader import ContextLoader

        pkg_path = tmp_pearl_dir / ".pearl" / "compiled-context-package.json"
        loader = ContextLoader(pkg_path)
        p1 = loader.load()
        p2 = loader.load()
        assert p1 is p2  # Same object (cached)

    def test_reload_on_mtime_change(self, tmp_pearl_dir):
        import hashlib
        from pearl_dev.context_loader import ContextLoader

        pkg_path = tmp_pearl_dir / ".pearl" / "compiled-context-package.json"
        loader = ContextLoader(pkg_path)
        p1 = loader.load()

        # Modify the file (recompute hash for new package_id)
        data = json.loads(pkg_path.read_text())
        data["package_metadata"]["package_id"] = "pkg_changed567890abcdef"
        check_data = {"project_id": "proj_test", "package_id": "pkg_changed567890abcdef"}
        canonical = json.dumps(check_data, sort_keys=True, separators=(",", ":"))
        new_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
        data["package_metadata"]["integrity"]["hash"] = new_hash
        pkg_path.write_text(json.dumps(data), encoding="utf-8")

        # Force different mtime
        import os
        os.utime(str(pkg_path), (time.time() + 10, time.time() + 10))

        p2 = loader.load()
        assert p1 is not p2  # Different object (reloaded)

    def test_missing_file_error(self, tmp_path):
        from pearl_dev.context_loader import ContextLoader

        loader = ContextLoader(tmp_path / "nonexistent.json")
        with pytest.raises(FileNotFoundError):
            loader.load()


# ═══════════════════════════════════════════════════════════════════════════
# Step 15: Policy Engine (CORE)
# ═══════════════════════════════════════════════════════════════════════════

class TestPolicyEngine:
    def test_allow_known_action(self, sample_package):
        from pearl_dev.policy_engine import Decision, PolicyEngine

        engine = PolicyEngine(sample_package)
        result = engine.check_action("code_edit")
        assert result.decision == Decision.ALLOW

    def test_block_known_action(self, sample_package):
        from pearl_dev.policy_engine import Decision, PolicyEngine

        engine = PolicyEngine(sample_package)
        result = engine.check_action("prod_deploy")
        assert result.decision == Decision.BLOCK
        assert "blocked_actions" in result.policy_ref

    def test_approval_required_action(self, sample_package):
        from pearl_dev.policy_engine import Decision, PolicyEngine

        engine = PolicyEngine(sample_package)
        result = engine.check_action("auth_flow_changes")
        assert result.decision == Decision.APPROVAL_REQUIRED

    def test_unknown_action_deny_by_default(self, sample_package):
        from pearl_dev.policy_engine import Decision, PolicyEngine

        engine = PolicyEngine(sample_package)
        result = engine.check_action("unknown_action_xyz")
        assert result.decision == Decision.BLOCK
        assert "deny-by-default" in result.reason

    def test_diff_catches_hardcoded_secret(self, sample_package):
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)
        diff = '+    api_key = "sk-1234567890abcdef1234567890"'
        violations = engine.check_diff(diff)
        assert len(violations) >= 1
        assert violations[0].pattern == "hardcoded_secrets"

    def test_diff_catches_private_key(self, sample_package):
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)
        diff = "+-----BEGIN RSA PRIVATE KEY-----"
        violations = engine.check_diff(diff)
        assert len(violations) >= 1
        assert violations[0].pattern == "hardcoded_secrets"

    def test_clean_diff_passes(self, sample_package):
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)
        diff = "+    result = compute_total(items)"
        violations = engine.check_diff(diff)
        assert len(violations) == 0

    def test_network_allow_listed_host(self, sample_package):
        from pearl_dev.policy_engine import Decision, PolicyEngine

        engine = PolicyEngine(sample_package)
        result = engine.check_network("llm-gateway.internal")
        assert result.decision == Decision.ALLOW

    def test_network_block_unlisted_host(self, sample_package):
        from pearl_dev.policy_engine import Decision, PolicyEngine

        engine = PolicyEngine(sample_package)
        result = engine.check_network("evil-server.example.com")
        assert result.decision == Decision.BLOCK

    def test_required_tests_for_feature(self, sample_package):
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)
        tests = engine.get_required_tests("feature")
        assert "authz_negative_tests" in tests
        assert "ai_disclosure_presence_test" in tests

    def test_required_tests_for_fix(self, sample_package):
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)
        tests = engine.get_required_tests("fix")
        assert len(tests) > 0

    def test_policy_summary_structure(self, sample_package):
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)
        summary = engine.get_policy_summary()
        assert summary["project_id"] == "proj_test"
        assert "allowed_actions" in summary
        assert "blocked_actions" in summary
        assert "prohibited_patterns" in summary

    def test_check_latency_under_50ms(self, sample_package):
        """Policy checks should complete in under 50ms."""
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)
        start = time.perf_counter()
        for _ in range(100):
            engine.check_action("code_edit")
            engine.check_action("prod_deploy")
            engine.check_action("unknown")
        elapsed = (time.perf_counter() - start) / 300  # avg per check
        assert elapsed < 0.05, f"Average check latency {elapsed:.4f}s exceeds 50ms"


# ═══════════════════════════════════════════════════════════════════════════
# Step 16: Local Task Packet Generator
# ═══════════════════════════════════════════════════════════════════════════

class TestTaskPacketLocal:
    def test_generate_with_affected_components(self, sample_package):
        from pearl_dev.task_packet_local import generate_task_packet_local

        packet = generate_task_packet_local(
            package=sample_package,
            task_type="feature",
            task_summary="Add login button",
            trace_id="trc_test1234",
            affected_components=["web-frontend"],
        )
        assert packet.task_packet_id.startswith("tp_")
        assert packet.project_id == "proj_test"
        assert "code_edit" in packet.allowed_actions

    def test_generate_without_components(self, sample_package):
        from pearl_dev.task_packet_local import generate_task_packet_local

        packet = generate_task_packet_local(
            package=sample_package,
            task_type="fix",
            task_summary="Fix bug in parser",
            trace_id="trc_test5678",
        )
        assert packet.task_type == "fix"
        assert len(packet.blocked_actions) > 0

    def test_approval_triggers_from_change_hints(self, sample_package):
        from pearl_dev.task_packet_local import generate_task_packet_local

        packet = generate_task_packet_local(
            package=sample_package,
            task_type="feature",
            task_summary="Change auth flow",
            trace_id="trc_test9999",
            change_hints=["auth_flow_change"],
        )
        assert "auth_flow_change" in packet.approval_triggers

    def test_context_budget_applied(self, sample_package):
        from pearl_dev.task_packet_local import generate_task_packet_local

        packet = generate_task_packet_local(
            package=sample_package,
            task_type="feature",
            task_summary="Small task",
            trace_id="trc_test0000",
            context_budget={"max_tokens_hint": 1024},
        )
        assert packet.context_budget is not None
        assert packet.context_budget.max_tokens_hint == 1024


# ═══════════════════════════════════════════════════════════════════════════
# Step 17: Audit Logger
# ═══════════════════════════════════════════════════════════════════════════

class TestAuditLogger:
    def test_append_entry(self, tmp_path):
        from pearl_dev.audit import AuditLogger

        audit = AuditLogger(tmp_path / "audit.jsonl")
        audit.log("action_check", "code_edit", "allow", reason="In allowed list")
        entries = audit.query()
        assert len(entries) == 1
        assert entries[0]["action"] == "code_edit"
        assert entries[0]["decision"] == "allow"

    def test_query_by_event_type(self, tmp_path):
        from pearl_dev.audit import AuditLogger

        audit = AuditLogger(tmp_path / "audit.jsonl")
        audit.log("action_check", "code_edit", "allow")
        audit.log("diff_check", "check_diff", "clean")
        audit.log("action_check", "prod_deploy", "block")

        results = audit.query(event_type="action_check")
        assert len(results) == 2

    def test_query_by_time_range(self, tmp_path):
        from pearl_dev.audit import AuditLogger

        audit = AuditLogger(tmp_path / "audit.jsonl")
        audit.log("action_check", "code_edit", "allow")

        # Query for entries after now (should be empty)
        future = datetime(2099, 1, 1, tzinfo=timezone.utc)
        results = audit.query(since=future)
        assert len(results) == 0

        # Query for entries after epoch (should get all)
        past = datetime(2000, 1, 1, tzinfo=timezone.utc)
        results = audit.query(since=past)
        assert len(results) == 1

    def test_concurrent_append(self, tmp_path):
        from pearl_dev.audit import AuditLogger

        audit = AuditLogger(tmp_path / "audit.jsonl")
        # Write multiple entries sequentially (simulates concurrent pattern)
        for i in range(10):
            audit.log("test", f"action_{i}", "allow")
        entries = audit.query()
        assert len(entries) == 10


# ═══════════════════════════════════════════════════════════════════════════
# Step 18: Approval Flow
# ═══════════════════════════════════════════════════════════════════════════

class TestApprovalFlow:
    def test_create_request(self, tmp_path):
        from pearl_dev.approval_terminal import ApprovalManager

        mgr = ApprovalManager(tmp_path / "approvals")
        req = mgr.request_approval("prod_deploy", "Need to deploy hotfix")
        assert req["approval_id"].startswith("appr_")
        assert req["status"] == "pending"

    def test_approve_request(self, tmp_path):
        from pearl_dev.approval_terminal import ApprovalManager

        mgr = ApprovalManager(tmp_path / "approvals")
        req = mgr.request_approval("prod_deploy", "Need to deploy")
        mgr.decide(req["approval_id"], "approve")
        checked = mgr.check_approval(req["approval_id"])
        assert checked["status"] == "approve"

    def test_reject_request(self, tmp_path):
        from pearl_dev.approval_terminal import ApprovalManager

        mgr = ApprovalManager(tmp_path / "approvals")
        req = mgr.request_approval("risky_action", "Want to do risky thing")
        mgr.decide(req["approval_id"], "reject", notes="Too risky")
        checked = mgr.check_approval(req["approval_id"])
        assert checked["status"] == "reject"
        assert checked["decision"]["notes"] == "Too risky"

    def test_list_pending(self, tmp_path):
        from pearl_dev.approval_terminal import ApprovalManager

        mgr = ApprovalManager(tmp_path / "approvals")
        mgr.request_approval("action_a", "Reason A")
        req_b = mgr.request_approval("action_b", "Reason B")
        mgr.decide(req_b["approval_id"], "approve")

        pending = mgr.list_pending()
        assert len(pending) == 1
        assert pending[0]["action"] == "action_a"


# ═══════════════════════════════════════════════════════════════════════════
# Step 19: MCP Server
# ═══════════════════════════════════════════════════════════════════════════

class TestMCPServer:
    def test_server_init(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        assert server is not None

    def test_tool_definitions(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        tools = server.get_tool_definitions()
        assert len(tools) == 9
        names = {t["name"] for t in tools}
        assert "pearl_check_action" in names
        assert "pearl_check_diff" in names
        assert "pearl_check_promotion" in names
        assert "pearl_register_repo" in names
        assert "pearl_get_governance_costs" in names

    def test_check_action_tool(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        result = server.handle_tool_call("pearl_check_action", {"action": "code_edit"})
        assert result["decision"] == "allow"

    def test_check_diff_tool(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        result = server.handle_tool_call(
            "pearl_check_diff",
            {"diff_text": "+    result = safe_function()"},
        )
        assert result["clean"] is True

    def test_get_task_context_tool(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        result = server.handle_tool_call(
            "pearl_get_task_context",
            {"task_type": "feature", "task_summary": "Add button"},
        )
        assert "task_packet_id" in result
        assert "allowed_actions" in result

    def test_request_approval_tool(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        result = server.handle_tool_call(
            "pearl_request_approval",
            {"action": "prod_deploy", "reason": "Need hotfix"},
        )
        assert result["status"] == "pending"
        assert result["approval_id"].startswith("appr_")

    def test_report_evidence_tool(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        result = server.handle_tool_call(
            "pearl_report_evidence",
            {"evidence_type": "test_results", "summary": "All tests passed"},
        )
        assert result["logged"] is True

    def test_get_policy_summary_tool(self, tmp_pearl_dir):
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=tmp_pearl_dir / ".pearl" / "compiled-context-package.json",
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        result = server.handle_tool_call("pearl_get_policy_summary", {})
        assert result["project_id"] == "proj_test"
        assert "allowed_actions" in result


# ═══════════════════════════════════════════════════════════════════════════
# Step 20: Hooks
# ═══════════════════════════════════════════════════════════════════════════

class TestHooks:
    def test_tool_action_mapping(self):
        from pearl_dev.hooks.pre_tool_call import TOOL_ACTION_MAP

        assert TOOL_ACTION_MAP["Bash"] == "code_edit"
        assert TOOL_ACTION_MAP["Write"] == "file_write"
        assert TOOL_ACTION_MAP["WebFetch"] == "web_search"
        assert TOOL_ACTION_MAP["Read"] == "file_read"

    def test_pre_hook_module_importable(self):
        import pearl_dev.hooks.pre_tool_call
        assert hasattr(pearl_dev.hooks.pre_tool_call, "main")

    def test_post_hook_module_importable(self):
        import pearl_dev.hooks.post_tool_call
        assert hasattr(pearl_dev.hooks.post_tool_call, "main")


# ═══════════════════════════════════════════════════════════════════════════
# Step 21: Templates
# ═══════════════════════════════════════════════════════════════════════════

class TestTemplates:
    def test_render_claude_md(self, sample_package):
        from pearl_dev.template_renderer import render_template

        result = render_template("CLAUDE.md.j2", sample_package)
        assert "proj_test" in result
        assert "PEARL:GOVERNANCE:BEGIN" in result
        assert "PEARL:GOVERNANCE:END" in result
        assert "pearl_check_action" in result
        assert "prod_deploy" in result  # blocked actions listed inline
        assert ".pearl/GOVERNANCE.md" in result

    def test_render_mcp_json(self, sample_package):
        from pearl_dev.template_renderer import render_template

        result = render_template("mcp.json.j2", sample_package, "/test/project")
        parsed = json.loads(result)
        assert "pearl" in parsed["mcpServers"]
        assert "unified_mcp" in parsed["mcpServers"]["pearl"]["args"][1]

    def test_render_cursorrules(self, sample_package):
        from pearl_dev.template_renderer import render_template

        result = render_template("cursorrules.j2", sample_package)
        assert "proj_test" in result
        assert "code_edit" in result
        assert "hardcoded_secrets" in result


# ═══════════════════════════════════════════════════════════════════════════
# Step 22: CLI
# ═══════════════════════════════════════════════════════════════════════════

class TestCLI:
    def test_init_creates_files(self, tmp_pearl_dir, monkeypatch):
        from pearl_dev.cli import main

        monkeypatch.chdir(tmp_pearl_dir)
        main(["init", "-d", str(tmp_pearl_dir)])

        assert (tmp_pearl_dir / "CLAUDE.md").exists()
        assert (tmp_pearl_dir / ".pearl" / "GOVERNANCE.md").exists()
        assert (tmp_pearl_dir / ".mcp.json").exists()
        assert (tmp_pearl_dir / ".cursorrules").exists()
        assert (tmp_pearl_dir / ".pearl" / "pearl-dev.toml").exists()

        # CLAUDE.md should have slim governance markers, not full policy
        claude_md = (tmp_pearl_dir / "CLAUDE.md").read_text(encoding="utf-8")
        assert "PEARL:GOVERNANCE:BEGIN" in claude_md
        assert "PEARL:GOVERNANCE:END" in claude_md
        assert ".pearl/GOVERNANCE.md" in claude_md

    def test_approve_and_reject(self, tmp_pearl_dir, monkeypatch):
        from pearl_dev.approval_terminal import ApprovalManager
        from pearl_dev.cli import main

        # Create pearl-dev.toml first
        toml_path = tmp_pearl_dir / ".pearl" / "pearl-dev.toml"
        toml_path.write_text(
            '[pearl-dev]\nproject_id = "proj_test"\n', encoding="utf-8"
        )

        monkeypatch.chdir(tmp_pearl_dir)

        # Create a request manually
        mgr = ApprovalManager(tmp_pearl_dir / ".pearl" / "approvals")
        req = mgr.request_approval("test_action", "Test reason")

        # Approve it
        main(["approve", req["approval_id"]])
        checked = mgr.check_approval(req["approval_id"])
        assert checked["status"] == "approve"

    def test_status_runs(self, tmp_pearl_dir, monkeypatch, capsys):
        from pearl_dev.cli import main

        toml_path = tmp_pearl_dir / ".pearl" / "pearl-dev.toml"
        toml_path.write_text(
            '[pearl-dev]\nproject_id = "proj_test"\n', encoding="utf-8"
        )

        monkeypatch.chdir(tmp_pearl_dir)
        main(["status"])
        captured = capsys.readouterr()
        assert "proj_test" in captured.out

    def test_audit_query(self, tmp_pearl_dir, monkeypatch, capsys):
        from pearl_dev.audit import AuditLogger
        from pearl_dev.cli import main

        toml_path = tmp_pearl_dir / ".pearl" / "pearl-dev.toml"
        toml_path.write_text(
            '[pearl-dev]\nproject_id = "proj_test"\n', encoding="utf-8"
        )

        # Write some audit entries
        audit = AuditLogger(tmp_pearl_dir / ".pearl" / "audit.jsonl")
        audit.log("action_check", "code_edit", "allow")

        monkeypatch.chdir(tmp_pearl_dir)
        main(["audit"])
        captured = capsys.readouterr()
        assert "code_edit" in captured.out


# ═══════════════════════════════════════════════════════════════════════════
# Step 23: Integration Test
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegration:
    def test_full_flow(self, tmp_pearl_dir, monkeypatch):
        """End-to-end: load -> init -> check action -> check diff -> audit."""
        from pearl_dev.audit import AuditLogger
        from pearl_dev.cli import main
        from pearl_dev.context_loader import ContextLoader
        from pearl_dev.policy_engine import Decision, PolicyEngine

        monkeypatch.chdir(tmp_pearl_dir)

        # 1. Load compiled context
        pkg_path = tmp_pearl_dir / ".pearl" / "compiled-context-package.json"
        loader = ContextLoader(pkg_path)
        package = loader.load()
        assert package.project_identity.project_id == "proj_test"

        # 2. Initialize pearl-dev
        main(["init", "-d", str(tmp_pearl_dir)])
        assert (tmp_pearl_dir / "CLAUDE.md").exists()

        # 3. Policy engine checks
        engine = PolicyEngine(package)
        assert engine.check_action("code_edit").decision == Decision.ALLOW
        assert engine.check_action("prod_deploy").decision == Decision.BLOCK
        assert engine.check_action("auth_flow_changes").decision == Decision.APPROVAL_REQUIRED

        # 4. Diff check
        violations = engine.check_diff('+  api_key = "sk-1234567890abcdef1234567890"')
        assert len(violations) > 0

        # 5. MCP server tool calls
        from pearl_dev.mcp_server import PearlDevMCPServer

        server = PearlDevMCPServer(
            package_path=pkg_path,
            audit_path=tmp_pearl_dir / ".pearl" / "audit.jsonl",
            approvals_dir=tmp_pearl_dir / ".pearl" / "approvals",
        )
        result = server.handle_tool_call("pearl_check_action", {"action": "code_edit"})
        assert result["decision"] == "allow"

        # 6. Verify audit log
        audit = AuditLogger(tmp_pearl_dir / ".pearl" / "audit.jsonl")
        entries = audit.query()
        assert len(entries) >= 1

    def test_hook_enforcement_simulation(self, tmp_pearl_dir, sample_package):
        """Simulate hook enforcement: allowed action passes, blocked action fails."""
        from pearl_dev.policy_engine import Decision, PolicyEngine

        engine = PolicyEngine(sample_package)

        # Simulate PreToolUse for allowed action
        result = engine.check_action("file_read")
        assert result.decision == Decision.ALLOW  # Would exit 0

        # Simulate PreToolUse for blocked action
        result = engine.check_action("prod_deploy")
        assert result.decision == Decision.BLOCK  # Would exit 1

    def test_latency_benchmark(self, sample_package):
        """All policy checks should complete in under 50ms each."""
        from pearl_dev.policy_engine import PolicyEngine

        engine = PolicyEngine(sample_package)

        operations = [
            lambda: engine.check_action("code_edit"),
            lambda: engine.check_action("prod_deploy"),
            lambda: engine.check_action("unknown"),
            lambda: engine.check_diff("+  x = 42"),
            lambda: engine.check_network("llm-gateway.internal"),
            lambda: engine.get_policy_summary(),
        ]

        for op in operations:
            start = time.perf_counter()
            op()
            elapsed = time.perf_counter() - start
            assert elapsed < 0.05, f"Operation took {elapsed:.4f}s (>50ms)"


# ═══════════════════════════════════════════════════════════════════════════
# Steps 25-30: MCP Entry Points, API Server, Config, Init Enhancements
# ═══════════════════════════════════════════════════════════════════════════

class TestMCPEntryPoints:
    def test_pearl_dev_mcp_server_has_main(self):
        """pearl_dev.mcp_server is importable and has PearlDevMCPServer."""
        import pearl_dev.mcp_server

        assert hasattr(pearl_dev.mcp_server, "PearlDevMCPServer")

    def test_pearl_dev_package_has_main(self):
        """pearl_dev package has __main__.py."""
        import importlib

        spec = importlib.util.find_spec("pearl_dev.__main__")
        assert spec is not None

    def test_pearl_api_mcp_stdio_server_importable(self):
        """pearl.mcp.stdio_server is importable."""
        from pearl.mcp.stdio_server import PearlAPIMCPStdioServer

        server = PearlAPIMCPStdioServer()
        assert server._mcp is not None

    def test_pearl_api_mcp_server_lists_28_tools(self):
        """pearl-api MCP server should expose 41 tools."""
        from pearl.mcp.stdio_server import PearlAPIMCPStdioServer

        server = PearlAPIMCPStdioServer()
        tools = server._mcp.list_tools()
        assert len(tools) == 41

    def test_pearl_api_mcp_stdio_main_importable(self):
        """pearl.mcp.stdio_server has main() entry point."""
        from pearl.mcp.stdio_server import main

        assert callable(main)


class TestConfigApiUrl:
    def test_config_default_api_url(self, tmp_pearl_dir):
        from pearl_dev.config import load_config

        toml_path = tmp_pearl_dir / ".pearl" / "pearl-dev.toml"
        toml_path.write_text(
            '[pearl-dev]\nproject_id = "proj_test"\n', encoding="utf-8"
        )
        config = load_config(tmp_pearl_dir)
        assert config.api_url == "http://localhost:8080/api/v1"

    def test_config_custom_api_url(self, tmp_pearl_dir):
        from pearl_dev.config import load_config

        toml_path = tmp_pearl_dir / ".pearl" / "pearl-dev.toml"
        toml_path.write_text(
            '[pearl-dev]\nproject_id = "proj_test"\napi_url = "http://custom:9090/api/v1"\n',
            encoding="utf-8",
        )
        config = load_config(tmp_pearl_dir)
        assert config.api_url == "http://custom:9090/api/v1"


class TestLocalServerMode:
    def test_local_mode_database_url(self, monkeypatch):
        monkeypatch.setenv("PEARL_LOCAL_MODE", "1")
        from pearl.config import Settings

        s = Settings()
        assert "sqlite" in s.effective_database_url

    def test_default_mode_database_url(self):
        from pearl.config import Settings

        s = Settings()
        assert "postgresql" in s.database_url

    def test_server_cli_importable(self):
        from pearl.server_cli import main

        assert callable(main)


class TestEnhancedInit:
    def test_init_creates_claude_settings(self, tmp_pearl_dir, monkeypatch):
        from pearl_dev.cli import main

        monkeypatch.chdir(tmp_pearl_dir)
        main(["init", "-d", str(tmp_pearl_dir)])

        settings_path = tmp_pearl_dir / ".claude" / "settings.json"
        assert settings_path.exists()
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "hooks" in data
        assert "PreToolUse" in data["hooks"]
        assert "PostToolUse" in data["hooks"]
        assert len(data["hooks"]["PreToolUse"]) == 1
        pre_hook = data["hooks"]["PreToolUse"][0]
        assert pre_hook["matcher"] == "*"
        assert "hooks" in pre_hook
        assert "pearl_dev.hooks.pre_tool_call" in pre_hook["hooks"][0]["command"]

    def test_init_skips_existing_settings(self, tmp_pearl_dir, monkeypatch):
        from pearl_dev.cli import main

        monkeypatch.chdir(tmp_pearl_dir)

        # Pre-create a settings file
        claude_dir = tmp_pearl_dir / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        settings_path = claude_dir / "settings.json"
        settings_path.write_text('{"existing": true}', encoding="utf-8")

        main(["init", "-d", str(tmp_pearl_dir)])

        # Should NOT be overwritten
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert data == {"existing": True}

    def test_mcp_json_includes_unified_server(self, tmp_pearl_dir, monkeypatch):
        from pearl_dev.cli import main

        monkeypatch.chdir(tmp_pearl_dir)
        main(["init", "-d", str(tmp_pearl_dir)])

        mcp_data = json.loads(
            (tmp_pearl_dir / ".mcp.json").read_text(encoding="utf-8")
        )
        assert "pearl" in mcp_data["mcpServers"]
        assert "pearl_dev.unified_mcp" in str(
            mcp_data["mcpServers"]["pearl"]["args"]
        )
