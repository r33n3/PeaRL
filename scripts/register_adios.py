"""Register aDiOS as a PeaRL project, attach all inputs, compile, and output the package.

Usage:
    python scripts/register_adios.py

Runs against the in-process PeaRL API (no server needed).
Outputs the compiled context package to:
    C:/Users/bradj/Development/aDiOS/.pearl/compiled-context-package.json
"""

import asyncio
import json
import sys
from pathlib import Path

# Ensure PeaRL src is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from pearl.db.base import Base
import pearl.db.models  # noqa: F401 - register all models
from pearl.main import create_app

# ── Output location ──────────────────────────────────────────────────────────
ADIOS_ROOT = Path("C:/Users/bradj/Development/aDiOS")
OUTPUT_DIR = ADIOS_ROOT / ".pearl"
OUTPUT_FILE = OUTPUT_DIR / "compiled-context-package.json"

# ── 1. Project ────────────────────────────────────────────────────────────────
PROJECT = {
    "schema_version": "1.1",
    "project_id": "proj_adios",
    "name": "aDiOS - AI-Distributed Operating System",
    "description": (
        "Local-first AI content creation platform that orchestrates LLM inference, "
        "image generation, voice synthesis, and multi-modal workflows on consumer "
        "hardware via PySide6 desktop GUI."
    ),
    "owner_team": "aDiOS Core",
    "business_criticality": "high",
    "external_exposure": "public",
    "ai_enabled": True,
}

# ── 2. Org Baseline ──────────────────────────────────────────────────────────
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
                "config_change",
                "tool_execution",
                "external_api_call",
                "file_system_write",
                "credential_access",
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
    "environment_defaults": {
        "dev": {
            "production_data_allowed": False,
            "approval_level": "standard",
        },
        "preprod": {
            "production_like_controls_required": True,
            "approval_level": "high",
        },
        "prod": {
            "approval_level": "strict",
            "autonomous_actions_default": "limited",
        },
    },
}

# ── 3. App Spec ───────────────────────────────────────────────────────────────
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
            {"name": "user_documents", "sensitivity": "confidential"},
            {"name": "api_keys_and_credentials", "sensitivity": "restricted"},
            {"name": "search_queries", "sensitivity": "internal"},
            {"name": "generated_images", "sensitivity": "internal"},
            {"name": "llm_context_window", "sensitivity": "confidential"},
            {"name": "voice_audio_streams", "sensitivity": "confidential"},
            {"name": "email_content", "sensitivity": "confidential"},
        ],
        "prohibited_in_model_context": [
            "api_keys",
            "smtp_credentials",
            "webhook_tokens",
            "raw_user_passwords",
        ],
    },
    "network": {
        "outbound_destinations": [
            {"host": "127.0.0.1:8080", "purpose": "local_llm_inference", "classification": "internal"},
            {"host": "lite.duckduckgo.com", "purpose": "web_search", "classification": "external"},
            {"host": "google.serper.dev", "purpose": "web_search", "classification": "external"},
            {"host": "knowledge-mcp.global.api.aws", "purpose": "mcp_tools", "classification": "external"},
            {"host": "configurable_smtp", "purpose": "email", "classification": "external"},
        ],
    },
    "controls": {
        "authentication": "none_local_desktop_single_user",
        "authorization": "tool_broker_path_sandboxing",
        "rate_limiting": "none_implemented",
        "input_validation": "tool_broker_policy_enforcement",
    },
    "integrity": {"signed": False},
}

# ── 4. Environment Profile ────────────────────────────────────────────────────
ENVIRONMENT_PROFILE = {
    "schema_version": "1.1",
    "profile_id": "envp_adios_dev_supervised",
    "environment": "dev",
    "delivery_stage": "prototype",
    "autonomy_mode": "supervised_autonomous",
    "risk_level": "high",
    "approval_level": "standard",
    "allowed_capabilities": [
        "code_edit",
        "test_create",
        "test_run",
        "config_edit",
        "local_llm_inference",
        "local_image_generation",
        "file_read",
        "file_write",
        "web_search",
    ],
    "blocked_capabilities": [
        "prod_deploy",
        "credential_rotation",
        "network_config_change",
        "external_api_key_generation",
        "smtp_send_without_approval",
        "mcp_server_registration",
    ],
}

# ── 5. Compile request ────────────────────────────────────────────────────────
COMPILE_REQUEST = {
    "schema_version": "1.1",
    "project_id": "proj_adios",
    "compile_options": {"apply_active_exceptions": True},
    "trace_id": "trc_adios_initial_compile",
}


async def main():
    # Set up in-memory DB and test client
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

        # Step 1: Create project
        print("1. Creating project 'proj_adios'...")
        r = await client.post("/api/v1/projects", json=PROJECT)
        assert r.status_code == 201, f"Create project failed: {r.status_code} {r.text}"
        print(f"   -> Project created: {r.json()['project_id']}")

        pid = "proj_adios"

        # Step 2: Attach org baseline
        print("2. Attaching org baseline...")
        r = await client.post(f"/api/v1/projects/{pid}/org-baseline", json=ORG_BASELINE)
        assert r.status_code == 200, f"Org baseline failed: {r.status_code} {r.text}"
        print(f"   -> Baseline attached: {r.json()['baseline_id']}")

        # Step 3: Attach app spec
        print("3. Attaching application spec...")
        r = await client.post(f"/api/v1/projects/{pid}/app-spec", json=APP_SPEC)
        assert r.status_code == 200, f"App spec failed: {r.status_code} {r.text}"
        print(f"   -> App spec attached: {r.json()['kind']}")

        # Step 4: Attach environment profile
        print("4. Attaching environment profile...")
        r = await client.post(f"/api/v1/projects/{pid}/environment-profile", json=ENVIRONMENT_PROFILE)
        assert r.status_code == 200, f"Env profile failed: {r.status_code} {r.text}"
        print(f"   -> Profile attached: {r.json()['profile_id']}")

        # Step 5: Compile context
        print("5. Compiling context...")
        r = await client.post(f"/api/v1/projects/{pid}/compile-context", json=COMPILE_REQUEST)
        assert r.status_code == 202, f"Compile failed: {r.status_code} {r.text}"
        job = r.json()
        print(f"   -> Compile job: {job['job_id']} (status: {job['status']})")

        # Step 6: Poll job
        r = await client.get(f"/api/v1/jobs/{job['job_id']}")
        assert r.status_code == 200
        print(f"   -> Job status: {r.json()['status']}")

        # Step 7: Retrieve compiled package
        print("6. Retrieving compiled context package...")
        r = await client.get(f"/api/v1/projects/{pid}/compiled-package")
        assert r.status_code == 200, f"Get package failed: {r.status_code} {r.text}"
        package = r.json()

        # Write to aDiOS directory
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        OUTPUT_FILE.write_text(json.dumps(package, indent=2), encoding="utf-8")

        print()
        print("=" * 72)
        print("  COMPILED CONTEXT PACKAGE GENERATED SUCCESSFULLY")
        print("=" * 72)
        print(f"  Output: {OUTPUT_FILE}")
        print(f"  Kind:   {package['kind']}")
        print(f"  Pkg ID: {package['package_metadata']['package_id']}")
        print(f"  Hash:   {package['package_metadata']['integrity']['hash']}")
        print()

        # Print summary
        print("  AUTONOMY POLICY")
        ap = package["autonomy_policy"]
        print(f"    Mode:             {ap['mode']}")
        print(f"    Allowed actions:  {ap['allowed_actions']}")
        print(f"    Blocked actions:  {ap['blocked_actions']}")
        print(f"    Approval needed:  {ap['approval_required_for']}")
        print()

        print("  SECURITY REQUIREMENTS")
        sr = package["security_requirements"]
        print(f"    Required controls:    {sr['required_controls']}")
        print(f"    Prohibited patterns:  {sr['prohibited_patterns']}")
        print()

        if "responsible_ai_requirements" in package:
            print("  RESPONSIBLE AI")
            rai = package["responsible_ai_requirements"]
            print(f"    AI disclosure required:         {rai['transparency']['ai_disclosure_required']}")
            print(f"    Model provenance logging:       {rai['transparency']['model_provenance_logging_required']}")
            print(f"    Fairness review required:       {rai['fairness']['review_required']}")
            print(f"    Human oversight for high-impact: {len(rai['oversight']['human_review_required_for'])} items")
            print()

        print("  NETWORK REQUIREMENTS")
        nr = package["network_requirements"]
        print(f"    Outbound allowlist:       {nr['outbound_allowlist']}")
        print(f"    Public egress forbidden:  {nr['public_egress_forbidden']}")
        print()

        print("  REQUIRED TESTS")
        rt = package["required_tests"]
        print(f"    Security:    {rt['security']}")
        print(f"    RAI:         {rt['rai']}")
        print(f"    Functional:  {rt['functional']}")
        print()

        print("  APPROVAL CHECKPOINTS")
        for cp in package["approval_checkpoints"]:
            print(f"    [{cp['checkpoint_id']}] trigger={cp['trigger']} roles={cp['required_roles']}")
        print()

        print("  REMEDIATION ELIGIBILITY")
        re = package["autonomous_remediation_eligibility"]
        print(f"    Default: {re['default']}")
        for rule in re.get("rules", []):
            print(f"    Rule: {rule['match']} -> {rule['eligibility']}")
        print()
        print("=" * 72)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
