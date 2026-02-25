"""Simulate findings from multiple security tools, ingest into PeaRL, and walk
through the full remediation -> approval -> exception -> recompile cycle.

Usage:
    python scripts/simulate_findings.py

Prereq: Run `python scripts/register_adios.py` first to create the project.
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pearl.db.base import Base
import pearl.db.models  # noqa: F401
from pearl.main import create_app

ADIOS_ROOT = Path("C:/Users/bradj/Development/aDiOS")
OUTPUT_DIR = ADIOS_ROOT / ".pearl"

# ── Simulated findings from multiple tools ────────────────────────────────

FINDINGS_BATCH = {
    "schema_version": "1.1",
    "source_batch": {
        "batch_id": "batch_sast_scan_20260221",
        "source_system": "multi-tool-pipeline",
        "connector_version": "2.1.0",
        "received_at": "2026-02-21T20:00:00Z",
        "trust_label": "trusted_internal",
    },
    "findings": [
        # ── Finding 1: SAST detected hardcoded API key ────────────────
        {
            "schema_version": "1.1",
            "finding_id": "find_sast_hardcoded_key_001",
            "source": {
                "tool_name": "semgrep",
                "tool_type": "sast",
                "trust_label": "trusted_internal",
                "raw_record_ref": "semgrep://rules/python.lang.security.hardcoded-api-key",
            },
            "project_id": "proj_adios",
            "environment": "dev",
            "category": "security",
            "severity": "high",
            "confidence": "high",
            "title": "Hardcoded API key in llm_client.py",
            "description": (
                "SAST scan found a hardcoded OpenAI-format API key on line 47 of "
                "src/adios/clients/llm_client.py. The key pattern matches "
                "'sk-...' and is committed to version control. This violates the "
                "org baseline rule 'secret_hardcoding_forbidden'."
            ),
            "affected_components": ["llm-client"],
            "control_refs": ["hardcoded_secrets", "audit_logging"],
            "exploitability": "high",
            "detected_at": "2026-02-21T19:45:00Z",
        },
        # ── Finding 2: SCA detected vulnerable dependency ─────────────
        {
            "schema_version": "1.1",
            "finding_id": "find_sca_vuln_dep_002",
            "source": {
                "tool_name": "pip-audit",
                "tool_type": "sca",
                "trust_label": "trusted_internal",
                "raw_record_ref": "GHSA-xxxx-yyyy-zzzz",
            },
            "project_id": "proj_adios",
            "environment": "dev",
            "category": "security",
            "severity": "critical",
            "confidence": "high",
            "title": "Critical RCE in httpx<0.28.1 (CVE-2026-FAKE-001)",
            "description": (
                "pip-audit detected that httpx==0.27.0 has a known remote code "
                "execution vulnerability. The fix is a pin update to httpx>=0.28.1. "
                "This is a dependency-only change with no code modifications needed."
            ),
            "affected_components": ["web-tools", "mcp-client"],
            "control_refs": ["input_validation"],
            "exploitability": "high",
            "detected_at": "2026-02-21T19:46:00Z",
        },
        # ── Finding 3: Manual review - missing auth boundary ──────────
        {
            "schema_version": "1.1",
            "finding_id": "find_manual_auth_003",
            "source": {
                "tool_name": "security-review",
                "tool_type": "manual",
                "trust_label": "manual_unverified",
            },
            "project_id": "proj_adios",
            "environment": "dev",
            "category": "security",
            "severity": "high",
            "confidence": "medium",
            "title": "Tool broker allows unauthenticated MCP tool registration",
            "description": (
                "During manual code review, the reviewer found that the tool-broker "
                "component accepts MCP tool registrations without verifying the "
                "caller's identity. An attacker on the local network could register "
                "a malicious MCP server and intercept tool calls. This crosses the "
                "'broker_to_mcp' trust boundary without proper validation."
            ),
            "affected_components": ["tool-broker", "mcp-client"],
            "control_refs": ["authz_checks", "tool_call_allowlisting"],
            "exploitability": "medium",
            "detected_at": "2026-02-21T19:50:00Z",
        },
        # ── Finding 4: RAI monitor - missing AI disclosure ────────────
        {
            "schema_version": "1.1",
            "finding_id": "find_rai_disclosure_004",
            "source": {
                "tool_name": "pearl-rai-scanner",
                "tool_type": "rai_monitor",
                "trust_label": "trusted_internal",
            },
            "project_id": "proj_adios",
            "environment": "dev",
            "category": "responsible_ai",
            "severity": "moderate",
            "confidence": "high",
            "title": "AI-generated content not disclosed in chat UI",
            "description": (
                "The gui-chat component displays LLM responses without any visual "
                "indicator that the content is AI-generated. The org baseline "
                "requires AI use disclosure for user-facing features. Users may "
                "mistake AI responses for human-written content."
            ),
            "affected_components": ["gui-chat", "intent-interpreter"],
            "control_refs": ["output_filtering"],
            "detected_at": "2026-02-21T19:52:00Z",
        },
        # ── Finding 5: DAST - undeclared external egress ──────────────
        {
            "schema_version": "1.1",
            "finding_id": "find_dast_egress_005",
            "source": {
                "tool_name": "burp-suite",
                "tool_type": "dast",
                "trust_label": "trusted_external_registered",
            },
            "project_id": "proj_adios",
            "environment": "dev",
            "category": "security",
            "severity": "moderate",
            "confidence": "high",
            "title": "Undeclared outbound call to analytics.example.com",
            "description": (
                "DAST proxy observed the application making HTTP requests to "
                "analytics.example.com which is not in the declared outbound "
                "allowlist. This egress was triggered during image generation "
                "workflows. The network policy states outbound connectivity must "
                "be declared and public egress is forbidden."
            ),
            "affected_components": ["image-generator"],
            "control_refs": ["undeclared_external_egress"],
            "exploitability": "low",
            "detected_at": "2026-02-21T19:55:00Z",
        },
    ],
    "options": {
        "normalize_on_ingest": True,
        "strict_validation": True,
        "quarantine_on_error": True,
    },
}

# ── Project setup data (same as register_adios.py) ───────────────────────

PROJECT = {
    "schema_version": "1.1",
    "project_id": "proj_adios",
    "name": "aDiOS - AI-Distributed Operating System",
    "description": "Local-first AI content creation platform.",
    "owner_team": "aDiOS Core",
    "business_criticality": "high",
    "external_exposure": "public",
    "ai_enabled": True,
}

ORG_BASELINE = {
    "schema_version": "1.1",
    "kind": "PearlOrgBaseline",
    "baseline_id": "orgb_adios_baseline",
    "org_name": "aDiOS Project",
    "defaults": {
        "coding": {
            "secure_coding_standard_required": True,
            "secret_hardcoding_forbidden": True,
            "dependency_pinning_required": True,
        },
        "logging": {
            "structured_logging_required": True,
            "pii_in_logs_forbidden_by_default": True,
            "security_events_minimum": [
                "config_change", "tool_execution", "external_api_call",
                "file_system_write", "credential_access",
            ],
        },
        "iam": {
            "least_privilege_required": True,
            "wildcard_permissions_forbidden_by_default": True,
        },
        "network": {
            "outbound_connectivity_must_be_declared": True,
            "deny_by_default_preferred": True,
        },
        "responsible_ai": {
            "ai_use_disclosure_required_for_user_facing": True,
            "model_provenance_logging_required": True,
            "fairness_review_required_when_user_impact_is_material": True,
            "human_oversight_required_for_high_impact_actions": True,
        },
        "testing": {
            "unit_tests_required": True,
            "security_tests_baseline_required": True,
            "rai_evals_required_for_ai_enabled_apps": True,
        },
    },
}

APP_SPEC = {
    "schema_version": "1.1",
    "kind": "PearlApplicationSpec",
    "application": {
        "app_id": "adios-desktop-ai",
        "owner_team": "adios-core",
        "business_criticality": "high",
        "external_exposure": "public",
        "ai_enabled": True,
    },
    "architecture": {
        "components": [
            {"id": "gui-chat", "type": "ui", "criticality": "moderate"},
            {"id": "intent-interpreter", "type": "service", "criticality": "high"},
            {"id": "plan-builder", "type": "service", "criticality": "high"},
            {"id": "plan-executor", "type": "service", "criticality": "critical"},
            {"id": "tool-broker", "type": "policy_enforcement", "criticality": "critical"},
            {"id": "llm-client", "type": "ai_gateway", "criticality": "high"},
            {"id": "image-generator", "type": "ai_gateway", "criticality": "moderate"},
            {"id": "voice-client", "type": "ai_gateway", "criticality": "moderate"},
            {"id": "web-tools", "type": "service", "criticality": "moderate"},
            {"id": "mcp-client", "type": "service", "criticality": "high"},
            {"id": "comm-tools", "type": "service", "criticality": "high"},
            {"id": "asset-layer", "type": "data_store", "criticality": "high"},
            {"id": "context-layer", "type": "data_store", "criticality": "high"},
        ],
        "trust_boundaries": [
            {"id": "user_to_gui", "from": "user", "to": "gui-chat"},
            {"id": "gui_to_intent", "from": "gui-chat", "to": "intent-interpreter"},
            {"id": "broker_to_llm", "from": "tool-broker", "to": "llm-client"},
            {"id": "broker_to_web", "from": "tool-broker", "to": "web-tools"},
            {"id": "broker_to_mcp", "from": "tool-broker", "to": "mcp-client"},
            {"id": "broker_to_comm", "from": "tool-broker", "to": "comm-tools"},
            {"id": "broker_to_fs", "from": "tool-broker", "to": "asset-layer"},
        ],
    },
    "data": {
        "classifications": [
            {"name": "chat_history", "sensitivity": "confidential"},
            {"name": "api_keys_and_credentials", "sensitivity": "restricted"},
            {"name": "llm_context_window", "sensitivity": "confidential"},
        ],
        "prohibited_in_model_context": [
            "api_keys", "smtp_credentials", "webhook_tokens", "raw_user_passwords",
        ],
    },
    "integrity": {"signed": False},
}

ENVIRONMENT_PROFILE = {
    "schema_version": "1.1",
    "profile_id": "envp_adios_dev_supervised",
    "environment": "dev",
    "delivery_stage": "prototype",
    "autonomy_mode": "supervised_autonomous",
    "risk_level": "high",
    "approval_level": "standard",
    "allowed_capabilities": [
        "code_edit", "test_create", "test_run", "config_edit",
        "local_llm_inference", "local_image_generation",
        "file_read", "file_write", "web_search",
    ],
    "blocked_capabilities": [
        "prod_deploy", "credential_rotation", "network_config_change",
        "external_api_key_generation", "smtp_send_without_approval",
        "mcp_server_registration",
    ],
}


def print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    app = create_app()
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    app.state.redis = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        pid = "proj_adios"

        # ── Phase 1: Set up the project (same as register script) ─────
        print_section("PHASE 1: PROJECT SETUP")

        r = await client.post("/api/v1/projects", json=PROJECT)
        assert r.status_code == 201, f"Create project: {r.status_code} {r.text}"
        print(f"  Project created: {r.json()['project_id']}")

        r = await client.post(f"/api/v1/projects/{pid}/org-baseline", json=ORG_BASELINE)
        assert r.status_code == 200, f"Org baseline: {r.status_code} {r.text}"
        print(f"  Org baseline attached: {r.json()['baseline_id']}")

        r = await client.post(f"/api/v1/projects/{pid}/app-spec", json=APP_SPEC)
        assert r.status_code == 200, f"App spec: {r.status_code} {r.text}"
        print(f"  App spec attached: {r.json()['kind']}")

        r = await client.post(f"/api/v1/projects/{pid}/environment-profile", json=ENVIRONMENT_PROFILE)
        assert r.status_code == 200, f"Env profile: {r.status_code} {r.text}"
        print(f"  Environment profile attached: {r.json()['profile_id']}")

        # ── Phase 2: Initial compile ──────────────────────────────────
        print_section("PHASE 2: INITIAL CONTEXT COMPILATION")

        r = await client.post(f"/api/v1/projects/{pid}/compile-context", json={
            "schema_version": "1.1", "project_id": pid,
            "compile_options": {"apply_active_exceptions": True},
            "trace_id": "trc_initial_compile",
        })
        assert r.status_code == 202
        job = r.json()
        print(f"  Compile job: {job['job_id']} (status: {job['status']})")

        r = await client.get(f"/api/v1/projects/{pid}/compiled-package")
        assert r.status_code == 200
        initial_pkg = r.json()
        initial_hash = initial_pkg["package_metadata"]["integrity"]["hash"]
        print(f"  Initial package compiled: {initial_pkg['package_metadata']['package_id']}")
        print(f"  Integrity hash: {initial_hash}")
        print(f"  Exceptions: {initial_pkg.get('exceptions', [])}")

        # ── Phase 3: Findings ingestion ───────────────────────────────
        print_section("PHASE 3: FINDINGS INGESTION (5 findings from 4 tools)")

        r = await client.post("/api/v1/findings/ingest", json=FINDINGS_BATCH)
        assert r.status_code == 202, f"Ingest: {r.status_code} {r.text}"
        ingest_result = r.json()
        print(f"  Batch: {ingest_result['batch_id']}")
        print(f"  Accepted: {ingest_result['accepted_count']}")
        print(f"  Quarantined: {ingest_result['quarantined_count']}")

        print()
        print("  Findings ingested:")
        for f in FINDINGS_BATCH["findings"]:
            tool = f["source"]["tool_name"]
            sev = f["severity"]
            cat = f["category"]
            print(f"    [{sev.upper():8s}] [{cat:15s}] {f['title'][:50]}... ({tool})")

        # ── Phase 4: Remediation spec generation ──────────────────────
        print_section("PHASE 4: REMEDIATION SPEC GENERATION")

        # 4a: Auto-eligible: dependency pin update (Finding 2)
        print()
        print("  4a. Dependency pin update (auto_allowed per compiled policy):")
        remed_dep = {
            "schema_version": "1.1",
            "project_id": pid,
            "environment": "dev",
            "finding_refs": ["find_sca_vuln_dep_002"],
            "trace_id": "trc_remed_dep_pin",
        }
        r = await client.post(f"/api/v1/projects/{pid}/remediation-specs/generate", json=remed_dep)
        assert r.status_code == 201, f"Remediation dep: {r.status_code} {r.text}"
        rs_dep = r.json()
        print(f"      Spec ID:      {rs_dep['remediation_spec_id']}")
        print(f"      Eligibility:  {rs_dep['eligibility']}")
        print(f"      Risk level:   {rs_dep['risk_summary']['risk_level']}")
        print(f"      Outcome:      {rs_dep['required_outcome']}")
        print(f"      Tests:        {rs_dep.get('required_tests', [])}")
        print(f"      Approval:     {rs_dep.get('approval_required', False)}")

        # 4b: Human-required: hardcoded secrets (Finding 1)
        print()
        print("  4b. Hardcoded API key (human_required — high severity secret):")
        remed_secret = {
            "schema_version": "1.1",
            "project_id": pid,
            "environment": "dev",
            "finding_refs": ["find_sast_hardcoded_key_001"],
            "trace_id": "trc_remed_secret",
        }
        r = await client.post(f"/api/v1/projects/{pid}/remediation-specs/generate", json=remed_secret)
        assert r.status_code == 201, f"Remediation secret: {r.status_code} {r.text}"
        rs_secret = r.json()
        print(f"      Spec ID:      {rs_secret['remediation_spec_id']}")
        print(f"      Eligibility:  {rs_secret['eligibility']}")
        print(f"      Risk level:   {rs_secret['risk_summary']['risk_level']}")
        print(f"      Outcome:      {rs_secret['required_outcome']}")
        print(f"      Approval:     {rs_secret.get('approval_required', False)}")

        # 4c: Auth boundary finding (Finding 3)
        print()
        print("  4c. MCP auth boundary (human_required — trust boundary issue):")
        remed_auth = {
            "schema_version": "1.1",
            "project_id": pid,
            "environment": "dev",
            "finding_refs": ["find_manual_auth_003"],
            "trace_id": "trc_remed_auth",
        }
        r = await client.post(f"/api/v1/projects/{pid}/remediation-specs/generate", json=remed_auth)
        assert r.status_code == 201
        rs_auth = r.json()
        print(f"      Spec ID:      {rs_auth['remediation_spec_id']}")
        print(f"      Eligibility:  {rs_auth['eligibility']}")
        print(f"      Risk level:   {rs_auth['risk_summary']['risk_level']}")
        print(f"      Approval:     {rs_auth.get('approval_required', False)}")

        # 4d: RAI disclosure (Finding 4)
        print()
        print("  4d. AI disclosure missing (human_required — RAI finding):")
        remed_rai = {
            "schema_version": "1.1",
            "project_id": pid,
            "environment": "dev",
            "finding_refs": ["find_rai_disclosure_004"],
            "trace_id": "trc_remed_rai",
        }
        r = await client.post(f"/api/v1/projects/{pid}/remediation-specs/generate", json=remed_rai)
        assert r.status_code == 201
        rs_rai = r.json()
        print(f"      Spec ID:      {rs_rai['remediation_spec_id']}")
        print(f"      Eligibility:  {rs_rai['eligibility']}")

        # ── Phase 5: Approval workflow ────────────────────────────────
        print_section("PHASE 5: APPROVAL WORKFLOW")

        # The auth boundary fix crosses the 'auth_flow_change' checkpoint
        print()
        print("  Creating approval request for auth boundary remediation...")
        approval_req = {
            "schema_version": "1.1",
            "approval_request_id": "appr_auth_fix_001",
            "project_id": pid,
            "environment": "dev",
            "request_type": "auth_flow_change",
            "trigger": "auth_flow_change",
            "requested_by": "autonomous-agent",
            "required_roles": ["security_review", "platform_owner"],
            "artifact_refs": [rs_auth["remediation_spec_id"]],
            "status": "pending",
            "created_at": "2026-02-21T20:10:00Z",
            "trace_id": "trc_approval_auth_fix",
        }
        r = await client.post("/api/v1/approvals/requests", json=approval_req)
        assert r.status_code == 201, f"Approval request: {r.status_code} {r.text}"
        appr = r.json()
        print(f"    Request ID:     {appr['approval_request_id']}")
        print(f"    Status:         {appr['status']}")
        print(f"    Required roles: {appr['required_roles']}")

        # Security reviewer approves
        print()
        print("  Security reviewer approves the auth fix...")
        decision = {
            "schema_version": "1.1",
            "approval_request_id": "appr_auth_fix_001",
            "decision": "approve",
            "decided_by": "security-lead@adios.dev",
            "decider_role": "security_review",
            "reason": "Auth boundary fix is critical. MCP tool registration must require caller verification.",
            "conditions": [
                "Must include integration tests for the new auth check",
                "Must not break existing MCP tool functionality",
            ],
            "decided_at": "2026-02-21T20:15:00Z",
            "trace_id": "trc_decision_auth_fix",
        }
        r = await client.post(
            "/api/v1/approvals/appr_auth_fix_001/decide", json=decision
        )
        assert r.status_code == 200, f"Decision: {r.status_code} {r.text}"
        dec = r.json()
        print(f"    Decision:       {dec['decision']}")
        print(f"    Decided by:     {dec['decided_by']}")
        print(f"    Conditions:     {dec.get('conditions', [])}")

        # ── Phase 6: Exception for known risk ─────────────────────────
        print_section("PHASE 6: EXCEPTION FOR KNOWN ACCEPTABLE RISK")

        print()
        print("  The undeclared egress to analytics.example.com is a known")
        print("  third-party analytics SDK. Creating a policy exception...")

        exception_req = {
            "schema_version": "1.1",
            "exception_id": "exc_analytics_egress_001",
            "project_id": pid,
            "scope": {
                "environment": "dev",
                "components": ["image-generator"],
                "controls": ["undeclared_external_egress"],
            },
            "requested_by": "platform-team@adios.dev",
            "rationale": (
                "analytics.example.com is a known SDK dependency of the image "
                "generation library. It sends anonymized telemetry only. "
                "Blocking it breaks image gen. Will add to allowlist in next "
                "app-spec update."
            ),
            "compensating_controls": [
                "Network proxy logging enabled for all outbound traffic",
                "SDK configured to disable PII collection",
                "30-day review cadence to update app-spec allowlist",
            ],
            "approved_by": ["security-lead@adios.dev", "platform-owner@adios.dev"],
            "status": "active",
            "start_at": "2026-02-21T20:20:00Z",
            "expires_at": "2026-03-23T20:20:00Z",
            "review_cadence_days": 30,
            "trace_id": "trc_exception_analytics",
        }
        r = await client.post("/api/v1/exceptions", json=exception_req)
        assert r.status_code == 201, f"Exception: {r.status_code} {r.text}"
        exc = r.json()
        print(f"    Exception ID:         {exc['exception_id']}")
        print(f"    Status:               {exc['status']}")
        print(f"    Scope:                {exc['scope']}")
        print(f"    Compensating controls: {len(exc['compensating_controls'])} items")
        print(f"    Expires:              {exc['expires_at']}")

        # ── Phase 7: Recompile with exception ─────────────────────────
        print_section("PHASE 7: RECOMPILE WITH ACTIVE EXCEPTION")

        print()
        print("  Recompiling context package with active exception overlay...")
        r = await client.post(f"/api/v1/projects/{pid}/compile-context", json={
            "schema_version": "1.1", "project_id": pid,
            "compile_options": {"apply_active_exceptions": True},
            "trace_id": "trc_recompile_with_exception",
        })
        assert r.status_code == 202
        job2 = r.json()
        print(f"  Recompile job: {job2['job_id']}")

        r = await client.get(f"/api/v1/projects/{pid}/compiled-package")
        assert r.status_code == 200
        recompiled_pkg = r.json()
        new_hash = recompiled_pkg["package_metadata"]["integrity"]["hash"]
        print(f"  New package:    {recompiled_pkg['package_metadata']['package_id']}")
        print(f"  New hash:       {new_hash}")
        print(f"  Hash changed:   {new_hash != initial_hash}")
        print(f"  Exceptions:     {recompiled_pkg.get('exceptions', [])}")

        # ── Phase 8: pearl-dev picks up new package ───────────────────
        print_section("PHASE 8: PEARL-DEV RELOADS NEW PACKAGE")

        # Write the recompiled package to aDiOS
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        recompiled_path = OUTPUT_DIR / "compiled-context-package.json"
        recompiled_path.write_text(json.dumps(recompiled_pkg, indent=2), encoding="utf-8")
        print(f"  Updated: {recompiled_path}")

        # Simulate pearl-dev loading the new package
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from pearl_dev.context_loader import ContextLoader
        from pearl_dev.policy_engine import PolicyEngine

        loader = ContextLoader(recompiled_path)
        new_package = loader.load(verify_integrity=True)
        policy_engine = PolicyEngine(new_package)

        print()
        print("  PolicyEngine reloaded with new context:")
        print(f"    Exceptions active: {new_package.exceptions}")
        print(f"    check_action('code_edit'):    {policy_engine.check_action('code_edit').decision}")
        print(f"    check_action('prod_deploy'):  {policy_engine.check_action('prod_deploy').decision}")
        print(f"    check_action('auth_flow_changes'): {policy_engine.check_action('auth_flow_changes').decision}")

        # ── Phase 9: Generate report ──────────────────────────────────
        print_section("PHASE 9: RELEASE READINESS REPORT")

        report_req = {
            "schema_version": "1.1",
            "report_type": "release_readiness",
            "format": "json",
            "filters": {"environment": "dev"},
        }
        r = await client.post(f"/api/v1/projects/{pid}/reports/generate", json=report_req)
        assert r.status_code in (200, 202), f"Report: {r.status_code} {r.text}"
        report = r.json()
        print(f"  Report ID:    {report.get('report_id', 'N/A')}")
        print(f"  Type:         {report.get('report_type', 'N/A')}")

        if "content" in report:
            content = report["content"]
            if isinstance(content, dict):
                print(f"  Ready:        {content.get('ready', 'N/A')}")
                blockers = content.get("blockers", [])
                print(f"  Blockers:     {len(blockers)}")
                for b in blockers:
                    print(f"    - {b}")

        # ── Summary ──────────────────────────────────────────────────
        print_section("SIMULATION COMPLETE — SUMMARY")
        print()
        print("  Findings ingested:     5 (from semgrep, pip-audit, manual review,")
        print("                           pearl-rai-scanner, burp-suite)")
        print(f"  Remediation specs:     4 generated")
        print(f"  Approval requests:     1 (auth_flow_change -> approved)")
        print(f"  Exceptions:            1 (analytics egress -> 30-day expiry)")
        print(f"  Recompilation:         Package hash changed ({initial_hash[:8]}... -> {new_hash[:8]}...)")
        print(f"  pearl-dev reloaded:    PolicyEngine updated with exception overlay")
        print()
        print("  WORKFLOW DEMONSTRATED:")
        print("    1. Project setup + initial compile")
        print("    2. External tools find issues -> ingest into PeaRL")
        print("    3. PeaRL generates remediation specs with eligibility:")
        print(f"       - Dep pin update:  {rs_dep['eligibility']}")
        print(f"       - Hardcoded key:   {rs_secret['eligibility']}")
        print(f"       - Auth boundary:   {rs_auth['eligibility']}")
        print(f"       - RAI disclosure:  {rs_rai['eligibility']}")
        print("    4. Approval workflow for auth boundary change")
        print("    5. Exception for known analytics egress")
        print("    6. Recompile picks up exception -> new hash")
        print("    7. pearl-dev hot-reloads new policy")
        print("    8. Release readiness report generated")
        print()
        print("=" * 72)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
