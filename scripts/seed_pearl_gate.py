"""Seed proj_feu data for GitHub branch protection demo.

Creates (idempotent):
  1. Project proj_feu
  2. Org baseline attached to proj_feu
  3. Environment profile (current env = sandbox)
  4. One critical finding — so the sandbox→dev gate starts blocked

Requires a running PeaRL server:
    PEARL_LOCAL=1 uvicorn pearl.main:app --reload --port 8081

Usage:
    python scripts/seed_pearl_gate.py [--api-url http://localhost:8081/api/v1]
"""

import argparse
import sys

import httpx


def main(api_url: str) -> None:
    client = httpx.Client(base_url=api_url, timeout=15.0)

    print(f"PeaRL API: {api_url}")
    print()

    # ── 1. Project ──────────────────────────────────────────────────────────
    print("1. Ensuring project proj_feu exists...")
    r = client.get("/projects/proj_feu")
    if r.status_code == 200:
        print("   -> Already exists, skipping.")
    else:
        r = client.post(
            "/projects",
            json={
                "schema_version": "1.1",
                "project_id": "proj_feu",
                "name": "PeaRL — Feature-Environment Underwriter",
                "description": (
                    "Self-referential PeaRL project used to demonstrate GitHub "
                    "branch protection via gate enforcement."
                ),
                "owner_team": "PeaRL Core",
                "business_criticality": "high",
                "external_exposure": "internal_only",
                "ai_enabled": True,
            },
        )
        if r.status_code not in (200, 201):
            print(f"   ERROR: {r.status_code} {r.text}", file=sys.stderr)
            sys.exit(1)
        print(f"   -> Created: {r.json().get('project_id')}")

    # ── 2. Org Baseline ─────────────────────────────────────────────────────
    print("2. Attaching org baseline...")
    r = client.post(
        "/projects/proj_feu/org-baseline",
        json={
            "schema_version": "1.1",
            "kind": "PearlOrgBaseline",
            "baseline_id": "orgb_feu_baseline",
            "org_name": "PeaRL Demo Org",
            "defaults": {
                "data_privacy": {},
                "security": {
                    "b004_2_rate_limits": True,
                    "b007_1_user_access_controls": True,
                },
                "safety": {
                    "c002_1_pre_deployment_test_approval": True,
                    "c003_1_harmful_output_filtering": True,
                },
                "reliability": {
                    "d003_1_tool_authorization_validation": True,
                    "d003_3_tool_call_log": True,
                },
                "accountability": {
                    "e004_1_change_approval_policy_records": True,
                    "e015_1_logging_implementation": True,
                    "e016_1_text_ai_disclosure": True,
                },
                "society": {},
            },
        },
    )
    if r.status_code not in (200, 201):
        print(f"   ERROR: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"   -> Baseline: {r.json().get('baseline_id')}")

    # ── 3. Environment Profile ───────────────────────────────────────────────
    print("3. Setting environment profile (sandbox)...")
    r = client.post(
        "/projects/proj_feu/environment-profile",
        json={
            "schema_version": "1.1",
            "profile_id": "envp_feu_sandbox",
            "environment": "sandbox",
            "delivery_stage": "prototype",
            "risk_level": "low",
            "autonomy_mode": "supervised_autonomous",
        },
    )
    if r.status_code not in (200, 201):
        print(f"   ERROR: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    print(f"   -> Profile: {r.json().get('profile_id', 'ok')}")

    # ── 4. Seed a critical finding (gate blocker) ────────────────────────────
    print("4. Seeding a critical finding (to demonstrate gate blocking)...")
    from datetime import datetime, timezone
    r = client.post(
        "/findings/ingest",
        json={
            "schema_version": "1.0",
            "source_batch": {
                "batch_id": "batch_seed_feu_001",
                "source_system": "seed_pearl_gate",
                "received_at": datetime.now(timezone.utc).isoformat(),
                "trust_label": "trusted_internal",
            },
            "findings": [
                {
                    "schema_version": "1.0",
                    "finding_id": "find_seed_feu_critical_001",
                    "project_id": "proj_feu",
                    "environment": "sandbox",
                    "category": "security",
                    "severity": "critical",
                    "title": "Hardcoded API key detected in source",
                    "description": (
                        "A hardcoded API key was found in src/config.py. "
                        "Must be moved to environment variables before promotion."
                    ),
                    "status": "open",
                    "detected_at": datetime.now(timezone.utc).isoformat(),
                    "source": {
                        "tool_name": "seed_pearl_gate",
                        "tool_type": "sast",
                        "trust_label": "trusted_internal",
                    },
                }
            ],
        },
    )
    if r.status_code not in (200, 201, 202):
        print(f"   WARNING: Could not create finding: {r.status_code} {r.text}")
    else:
        print(f"   -> Finding ingested (batch accepted: {r.json().get('accepted_count', '?')})")

    # ── 5. Confirm gate evaluation ───────────────────────────────────────────
    print()
    print("5. Running gate evaluation (sandbox → dev)...")
    r = client.post(
        "/projects/proj_feu/promotions/evaluate"
        "?source_environment=sandbox&target_environment=dev"
    )
    if r.status_code != 200:
        print(f"   ERROR: {r.status_code} {r.text}", file=sys.stderr)
        sys.exit(1)
    ev = r.json()
    print(f"   -> Gate status : {ev.get('status')}")
    print(f"   -> Passed      : {ev.get('passed_count')}/{ev.get('total_count')}")
    print(f"   -> Blockers    : {ev.get('blockers') or '(none)'}")

    print()
    print("=" * 60)
    print("  proj_feu seeded successfully")
    print("=" * 60)
    if ev.get("status") != "passed":
        print()
        print("  Gate is BLOCKED — expected for the demo.")
        print("  Contest the failing rule(s) via the PeaRL dashboard")
        print("  and re-evaluate to unblock the PR.")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed proj_feu data in PeaRL")
    parser.add_argument(
        "--api-url",
        default="http://localhost:8081/api/v1",
        help="PeaRL API base URL (default: http://localhost:8081/api/v1)",
    )
    args = parser.parse_args()
    main(args.api_url)
