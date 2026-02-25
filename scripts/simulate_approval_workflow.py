"""Demonstrate how the PeaRL approval workflow adjusts per environment.

Shows the same action (auth_flow_change) flowing through the PeaRL API
across three environments (dev, preprod, prod) with escalating approval
requirements driven by each environment's approval_level.

Usage:
    python scripts/simulate_approval_workflow.py

Prereq: None (uses in-memory DB).
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
APPROVALS_DIR = OUTPUT_DIR / "approvals"

# ── Shared project + org baseline + app spec ───────────────────────────

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
            {"id": "tool-broker", "type": "policy_enforcement", "criticality": "critical"},
            {"id": "llm-client", "type": "ai_gateway", "criticality": "high"},
            {"id": "mcp-client", "type": "service", "criticality": "high"},
        ],
        "trust_boundaries": [
            {"id": "user_to_gui", "from": "user", "to": "gui-chat"},
            {"id": "broker_to_mcp", "from": "tool-broker", "to": "mcp-client"},
        ],
    },
    "data": {
        "classifications": [
            {"name": "api_keys_and_credentials", "sensitivity": "restricted"},
        ],
        "prohibited_in_model_context": ["api_keys", "raw_user_passwords"],
    },
    "integrity": {"signed": False},
}

# ── Three environment profiles with different approval levels ──────────

ENV_PROFILES = {
    "dev": {
        "schema_version": "1.1",
        "profile_id": "envp_adios_dev",
        "environment": "dev",
        "delivery_stage": "prototype",
        "autonomy_mode": "supervised_autonomous",
        "risk_level": "moderate",
        "approval_level": "standard",
        "allowed_capabilities": [
            "code_edit", "test_create", "test_run", "config_edit",
            "local_llm_inference", "file_read", "file_write", "web_search",
        ],
        "blocked_capabilities": [
            "prod_deploy", "credential_rotation", "network_config_change",
        ],
    },
    "preprod": {
        "schema_version": "1.1",
        "profile_id": "envp_adios_preprod",
        "environment": "preprod",
        "delivery_stage": "hardening",
        "autonomy_mode": "supervised_autonomous",
        "risk_level": "high",
        "approval_level": "high",
        "allowed_capabilities": [
            "code_edit", "test_run", "config_edit", "file_read",
        ],
        "blocked_capabilities": [
            "prod_deploy", "credential_rotation", "network_config_change",
            "external_api_key_generation", "mcp_server_registration",
            "file_write", "web_search",
        ],
    },
    "prod": {
        "schema_version": "1.1",
        "profile_id": "envp_adios_prod",
        "environment": "prod",
        "delivery_stage": "prod",
        "autonomy_mode": "read_only",
        "risk_level": "critical",
        "approval_level": "strict",
        "allowed_capabilities": [
            "file_read", "test_run",
        ],
        "blocked_capabilities": [
            "code_edit", "config_edit", "prod_deploy", "credential_rotation",
            "network_config_change", "external_api_key_generation",
            "mcp_server_registration", "file_write", "web_search",
            "local_llm_inference",
        ],
    },
}

# ── Who can approve in each environment ────────────────────────────────

APPROVERS = {
    "dev": {
        "decided_by": "security-lead@adios.dev",
        "decider_role": "security_review",
    },
    "preprod": {
        "decided_by": "security-lead@adios.dev",
        "decider_role": "security_review",
    },
    "prod": {
        "decided_by": "cto@adios.dev",
        "decider_role": "exec_sponsor",
    },
}


def print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def print_checkpoints(checkpoints: list[dict]) -> None:
    for cp in checkpoints:
        trigger = cp["trigger"]
        roles = ", ".join(cp.get("required_roles") or [])
        env = cp.get("environment", "any")
        print(f"    [{trigger:30s}] roles: [{roles}] env: {env}")


async def main():
    engine = create_async_engine("sqlite+aiosqlite:///", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    app = create_app()
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    app.state.redis = None

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:

        pid = "proj_adios"

        # ── Phase 1: Create project with org baseline + app spec ───────
        print_section("PHASE 1: PROJECT SETUP (shared across all environments)")

        r = await client.post("/api/v1/projects", json=PROJECT)
        assert r.status_code == 201, f"Create project: {r.status_code} {r.text}"
        print(f"  Project: {r.json()['project_id']}")

        r = await client.post(f"/api/v1/projects/{pid}/org-baseline", json=ORG_BASELINE)
        assert r.status_code == 200
        print(f"  Org baseline: {r.json()['baseline_id']}")

        r = await client.post(f"/api/v1/projects/{pid}/app-spec", json=APP_SPEC)
        assert r.status_code == 200
        print(f"  App spec: {r.json()['kind']}")

        # ── Phase 2: Compile for each environment, compare checkpoints ─
        print_section("PHASE 2: COMPILE ACROSS 3 ENVIRONMENTS")
        print()
        print("  Same project, same app spec, same org baseline.")
        print("  Only the environment profile changes.")
        print("  Watch how approval checkpoints escalate.")

        compiled_packages = {}

        for env_name in ("dev", "preprod", "prod"):
            env_profile = ENV_PROFILES[env_name]
            level = env_profile["approval_level"]

            print()
            print(f"  --- {env_name.upper()} (approval_level={level}) ---")

            # Attach environment profile (re-attach overwrites previous)
            r = await client.post(
                f"/api/v1/projects/{pid}/environment-profile",
                json=env_profile,
            )
            assert r.status_code == 200, f"Env profile {env_name}: {r.status_code} {r.text}"
            print(f"    Profile: {r.json()['profile_id']}")

            # Compile context
            r = await client.post(
                f"/api/v1/projects/{pid}/compile-context",
                json={
                    "schema_version": "1.1",
                    "project_id": pid,
                    "compile_options": {"apply_active_exceptions": True},
                    "trace_id": f"trc_compile_{env_name}",
                },
            )
            assert r.status_code == 202, f"Compile {env_name}: {r.status_code} {r.text}"

            r = await client.get(f"/api/v1/projects/{pid}/compiled-package")
            assert r.status_code == 200
            pkg = r.json()
            compiled_packages[env_name] = pkg

            checkpoints = pkg.get("approval_checkpoints", [])
            print(f"    Checkpoints ({len(checkpoints)}):")
            print_checkpoints(checkpoints)

        # ── Phase 3: Compare checkpoints side-by-side ──────────────────
        print_section("PHASE 3: APPROVAL CHECKPOINT COMPARISON")
        print()
        print(f"  {'Trigger':<32s} {'DEV (standard)':<18s} {'PREPROD (high)':<18s} {'PROD (strict)':<18s}")
        print(f"  {'-'*32} {'-'*18} {'-'*18} {'-'*18}")

        all_triggers = set()
        for env_name in ("dev", "preprod", "prod"):
            for cp in compiled_packages[env_name].get("approval_checkpoints", []):
                all_triggers.add(cp["trigger"])

        for trigger in sorted(all_triggers):
            row = f"  {trigger:<32s}"
            for env_name in ("dev", "preprod", "prod"):
                cps = compiled_packages[env_name].get("approval_checkpoints", [])
                match = [cp for cp in cps if cp["trigger"] == trigger]
                if match:
                    roles = match[0].get("required_roles", [])
                    row += f" {len(roles)} roles".ljust(18)
                else:
                    row += " --".ljust(18)
            print(row)

        # ── Phase 4: Same action across environments ───────────────────
        print_section("PHASE 4: APPROVAL WORKFLOW - auth_flow_change")
        print()
        print("  Scenario: An autonomous agent wants to modify the MCP tool")
        print("  broker's authentication flow. This crosses the 'auth_flow_change'")
        print("  checkpoint. Watch how the process differs per environment.")

        approval_outputs = {}

        for env_name in ("dev", "preprod", "prod"):
            pkg = compiled_packages[env_name]
            level = ENV_PROFILES[env_name]["approval_level"]

            print()
            print(f"  --- {env_name.upper()} (approval_level={level}) ---")

            # Find the auth_flow_change checkpoint for this environment
            checkpoints = pkg.get("approval_checkpoints", [])
            auth_cp = [cp for cp in checkpoints if cp["trigger"] == "auth_flow_change"]

            if not auth_cp:
                print(f"    No auth_flow_change checkpoint in {env_name} -- action allowed.")
                approval_outputs[env_name] = {
                    "environment": env_name,
                    "approval_level": level,
                    "checkpoint_exists": False,
                    "action": "auth_flow_change",
                    "result": "no_checkpoint_required",
                }
                continue

            required_roles = auth_cp[0].get("required_roles", [])
            print(f"    Checkpoint:      {auth_cp[0]['checkpoint_id']}")
            print(f"    Required roles:  {required_roles}")

            # Create approval request through the PeaRL API
            appr_id = f"appr_auth_{env_name}_001"
            approval_req = {
                "schema_version": "1.1",
                "approval_request_id": appr_id,
                "project_id": pid,
                "environment": env_name,
                "request_type": "auth_flow_change",
                "trigger": "auth_flow_change",
                "requested_by": "autonomous-agent",
                "required_roles": required_roles,
                "artifact_refs": [f"remed_auth_boundary_{env_name}"],
                "status": "pending",
                "created_at": "2026-02-21T21:00:00Z",
                "trace_id": f"trc_appr_{env_name}",
            }
            r = await client.post("/api/v1/approvals/requests", json=approval_req)
            assert r.status_code == 201, f"Approval {env_name}: {r.status_code} {r.text}"
            appr = r.json()
            print(f"    Request created: {appr['approval_request_id']}")
            print(f"    Status:          {appr['status']}")

            # Simulate the appropriate approver deciding
            approver = APPROVERS[env_name]
            conditions = []
            if env_name == "preprod":
                conditions = [
                    "Must pass integration test suite before merge",
                    "Security regression tests must pass",
                ]
            elif env_name == "prod":
                conditions = [
                    "Requires passing preprod validation first",
                    "Must pass full security regression suite",
                    "Change window: next scheduled maintenance",
                    "Rollback plan documented and reviewed",
                ]

            decision_payload = {
                "schema_version": "1.1",
                "approval_request_id": appr_id,
                "decision": "approve",
                "decided_by": approver["decided_by"],
                "decider_role": approver["decider_role"],
                "reason": f"Auth boundary fix approved for {env_name} environment.",
                "conditions": conditions if conditions else None,
                "decided_at": "2026-02-21T21:05:00Z",
                "trace_id": f"trc_decision_{env_name}",
            }
            r = await client.post(
                f"/api/v1/approvals/{appr_id}/decide", json=decision_payload
            )
            assert r.status_code == 200, f"Decision {env_name}: {r.status_code} {r.text}"
            dec = r.json()
            print(f"    Decision:        {dec['decision']}")
            print(f"    Decided by:      {dec['decided_by']} ({dec['decider_role']})")
            if dec.get("conditions"):
                print(f"    Conditions ({len(dec['conditions'])}):")
                for c in dec["conditions"]:
                    print(f"      - {c}")

            approval_outputs[env_name] = {
                "environment": env_name,
                "approval_level": level,
                "checkpoint_exists": True,
                "checkpoint_id": auth_cp[0]["checkpoint_id"],
                "action": "auth_flow_change",
                "required_roles": required_roles,
                "request": {
                    "approval_request_id": appr_id,
                    "requested_by": "autonomous-agent",
                    "status": "pending",
                    "created_at": "2026-02-21T21:00:00Z",
                },
                "decision": {
                    "decision": dec["decision"],
                    "decided_by": dec["decided_by"],
                    "decider_role": dec["decider_role"],
                    "conditions": dec.get("conditions"),
                    "decided_at": "2026-02-21T21:05:00Z",
                },
                "result": "approved",
            }

        # ── Phase 5: Write approval artifacts to aDiOS ─────────────────
        print_section("PHASE 5: APPROVAL ARTIFACTS -> aDiOS")
        print()
        print("  Writing API-sourced approval records to .pearl/approvals/")

        APPROVALS_DIR.mkdir(parents=True, exist_ok=True)

        for env_name, output in approval_outputs.items():
            filename = f"appr_auth_flow_{env_name}.json"
            filepath = APPROVALS_DIR / filename
            filepath.write_text(json.dumps(output, indent=2), encoding="utf-8")
            print(f"    {filepath}")

        # ── Phase 6: Write the prod compiled package to aDiOS ──────────
        print_section("PHASE 6: PROD COMPILED PACKAGE -> aDiOS")
        print()
        print("  Writing the prod-compiled context package (strictest policy)")

        prod_pkg_path = OUTPUT_DIR / "compiled-context-package-prod.json"
        prod_pkg_path.write_text(
            json.dumps(compiled_packages["prod"], indent=2), encoding="utf-8"
        )
        print(f"    {prod_pkg_path}")
        prod_checkpoints = compiled_packages["prod"].get("approval_checkpoints", [])
        print(f"    Checkpoints: {len(prod_checkpoints)}")
        for cp in prod_checkpoints:
            print(f"      - {cp['trigger']}: {cp.get('required_roles', [])}")

        # ── Summary ────────────────────────────────────────────────────
        print_section("SUMMARY: ENVIRONMENT-DRIVEN APPROVAL GOVERNANCE")
        print()
        print("  The same action (auth_flow_change) requires different approval")
        print("  processes depending on which environment the team is working in:")
        print()

        for env_name in ("dev", "preprod", "prod"):
            level = ENV_PROFILES[env_name]["approval_level"]
            pkg = compiled_packages[env_name]
            n_cp = len(pkg.get("approval_checkpoints", []))
            auth_cp = [cp for cp in pkg.get("approval_checkpoints", [])
                       if cp["trigger"] == "auth_flow_change"]
            if auth_cp:
                roles = auth_cp[0].get("required_roles", [])
                roles_str = ", ".join(roles)
            else:
                roles_str = "(no checkpoint)"

            output = approval_outputs[env_name]
            conditions_count = 0
            if output.get("decision") and output["decision"].get("conditions"):
                conditions_count = len(output["decision"]["conditions"])

            print(f"  {env_name.upper():8s} | level={level:8s} | {n_cp} checkpoints | "
                  f"auth_flow roles: [{roles_str}] | {conditions_count} conditions")

        print()
        print("  KEY TAKEAWAYS:")
        print("    1. approval_level in the environment profile drives checkpoint count")
        print("    2. Higher environments require more roles to approve")
        print("    3. Strict (prod) adds exec_sponsor to every checkpoint")
        print("    4. Conditions escalate: dev=none, preprod=testing, prod=full change mgmt")
        print("    5. All approvals flow through the PeaRL API (not static files)")
        print("    6. pearl-dev reads the compiled package -> PolicyEngine enforces locally")
        print()
        print("  FILES WRITTEN TO aDiOS:")
        print(f"    {APPROVALS_DIR}/appr_auth_flow_dev.json")
        print(f"    {APPROVALS_DIR}/appr_auth_flow_preprod.json")
        print(f"    {APPROVALS_DIR}/appr_auth_flow_prod.json")
        print(f"    {OUTPUT_DIR}/compiled-context-package-prod.json")
        print()
        print("=" * 72)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
