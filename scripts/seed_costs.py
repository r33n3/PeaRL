"""
Seed cost ledger entries (ClientCostEntryRow) for demo projects.

Cost in PeaRL is derived from AI agent workflow runs pushed by pearl-dev clients:
  - Each workflow (security scan, context compile, RAI eval, attack surface, etc.)
    records the model used, cost in USD, duration, and tool calls.
  - The project overview sums all entries → total_cost_usd.

We seed realistic entries matching each project's history:
  - More entries for mature prod projects (many pipeline runs over months)
  - Fewer for newer dev/preprod projects
  - Mix of models (claude-opus-4-5 for deep analysis, claude-haiku-4-5 for fast scans)
  - Workflows: security_scan, rai_evaluation, context_compile, attack_surface,
               workflow_analysis, mcp_analysis, compliance_check, guardrail_verify
"""

import sys
from pathlib import Path
import httpx
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

API = "http://localhost:8080/api/v1"

# Workflow cost profiles: (workflow, model, avg_cost, avg_duration_ms, avg_turns, tools)
WORKFLOWS = {
    "security_scan": (
        "claude-sonnet-4-6", 0.38, 42000, 12,
        ["read_file", "grep_search", "run_semgrep", "check_secrets", "list_findings"],
    ),
    "rai_evaluation": (
        "claude-opus-4-6", 1.24, 95000, 28,
        ["read_policy", "analyze_outputs", "check_fairness", "score_alignment", "write_report"],
    ),
    "context_compile": (
        "claude-haiku-4-5", 0.07, 8000, 4,
        ["read_manifest", "collect_metadata", "build_context"],
    ),
    "attack_surface": (
        "claude-sonnet-4-6", 0.55, 61000, 17,
        ["enumerate_endpoints", "check_auth", "probe_inputs", "map_dependencies"],
    ),
    "workflow_analysis": (
        "claude-sonnet-4-6", 0.42, 48000, 14,
        ["trace_execution", "check_guardrails", "verify_logging", "review_rollback"],
    ),
    "mcp_analysis": (
        "claude-sonnet-4-6", 0.31, 35000, 10,
        ["list_tools", "check_permissions", "verify_tool_safety", "audit_calls"],
    ),
    "compliance_check": (
        "claude-opus-4-6", 0.89, 78000, 22,
        ["load_framework", "map_controls", "score_coverage", "flag_gaps", "write_report"],
    ),
    "guardrail_verify": (
        "claude-haiku-4-5", 0.09, 11000, 5,
        ["load_rules", "test_inputs", "check_blocks", "report_coverage"],
    ),
    "mass_scan": (
        "claude-sonnet-4-6", 0.67, 74000, 19,
        ["enumerate_components", "run_probes", "classify_risks", "aggregate_results"],
    ),
    "security_review": (
        "claude-opus-4-6", 1.58, 110000, 34,
        ["deep_code_review", "architecture_review", "threat_model", "pen_test_surface", "write_report"],
    ),
    "incident_drill": (
        "claude-sonnet-4-6", 0.29, 32000, 9,
        ["simulate_incident", "test_runbooks", "verify_alerting"],
    ),
    "model_drift_check": (
        "claude-haiku-4-5", 0.12, 14000, 6,
        ["pull_metrics", "compare_baseline", "flag_drift", "write_summary"],
    ),
}


def entry(workflow: str, env: str, ts: str, jitter_cost: float = 0.0, success: bool = True):
    model, base_cost, dur_ms, turns, tools = WORKFLOWS[workflow]
    cost = round(base_cost + jitter_cost, 4)
    return {
        "timestamp": ts,
        "environment": env,
        "workflow": workflow,
        "model": model,
        "cost_usd": cost,
        "duration_ms": dur_ms,
        "num_turns": turns,
        "tools_called": tools,
        "tool_count": len(tools),
        "success": success,
        "session_id": f"sess_{workflow[:8]}_{ts[:10].replace('-','')}",
    }


def push(project_id: str, entries: list[dict]):
    c = httpx.Client(base_url=API, timeout=30)
    r = c.post(f"/projects/{project_id}/governance-costs", json={"entries": entries})
    total = sum(e["cost_usd"] for e in entries)
    if r.status_code in (200, 201):
        print(f"  ✓  {project_id:<22}  {len(entries):>3} entries  ${total:>7.2f}")
    else:
        print(f"  ✗  {project_id:<22}  {r.status_code}: {r.text[:120]}")


def main():
    print()
    print("  PeaRL Cost Ledger Seed")
    print()
    print("  Cost = sum of AI agent workflow runs (security scans, RAI evals, etc.)")
    print()

    # ── FraudShield (prod, mission_critical) ─────────────────────────────
    # Mature project — many runs over 3 months. Heavy RAI + compliance.
    push("proj_fraudshield", [
        # Dev phase (d90–d70)
        entry("context_compile",  "dev",     "2025-12-05T10:00:00Z"),
        entry("security_scan",    "dev",     "2025-12-08T14:00:00Z"),
        entry("security_scan",    "dev",     "2025-12-12T09:00:00Z"),
        entry("guardrail_verify", "dev",     "2025-12-15T11:00:00Z"),
        entry("rai_evaluation",   "dev",     "2025-12-18T14:00:00Z", 0.15),
        entry("workflow_analysis","dev",     "2025-12-20T10:00:00Z"),
        entry("attack_surface",   "dev",     "2025-12-22T15:00:00Z"),
        entry("mcp_analysis",     "dev",     "2025-12-23T10:00:00Z"),
        entry("compliance_check", "dev",     "2025-12-24T13:00:00Z", 0.20),
        # Preprod phase (d70–d40)
        entry("context_compile",  "preprod", "2025-12-25T10:00:00Z"),
        entry("security_scan",    "preprod", "2025-12-28T14:00:00Z"),
        entry("security_scan",    "preprod", "2026-01-04T09:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-01-07T14:00:00Z", 0.22),
        entry("attack_surface",   "preprod", "2026-01-10T15:00:00Z"),
        entry("mass_scan",        "preprod", "2026-01-12T10:00:00Z"),
        entry("compliance_check", "preprod", "2026-01-15T13:00:00Z", 0.18),
        entry("security_review",  "preprod", "2026-01-18T10:00:00Z", 0.30),
        entry("workflow_analysis","preprod", "2026-01-20T14:00:00Z"),
        entry("guardrail_verify", "preprod", "2026-01-22T11:00:00Z"),
        # Prod phase (d40–now, recurring monitoring)
        entry("context_compile",  "prod",    "2026-01-24T10:00:00Z"),
        entry("security_scan",    "prod",    "2026-01-28T09:00:00Z"),
        entry("model_drift_check","prod",    "2026-01-31T08:00:00Z"),
        entry("guardrail_verify", "prod",    "2026-02-03T11:00:00Z"),
        entry("security_scan",    "prod",    "2026-02-07T09:00:00Z"),
        entry("model_drift_check","prod",    "2026-02-10T08:00:00Z"),
        entry("compliance_check", "prod",    "2026-02-12T13:00:00Z"),
        entry("incident_drill",   "prod",    "2026-02-14T14:00:00Z"),
        entry("security_scan",    "prod",    "2026-02-17T09:00:00Z"),
        entry("model_drift_check","prod",    "2026-02-21T08:00:00Z"),
        entry("rai_evaluation",   "prod",    "2026-02-24T14:00:00Z", 0.10),
        entry("security_scan",    "prod",    "2026-02-28T09:00:00Z"),
        entry("model_drift_check","prod",    "2026-03-03T08:00:00Z"),
        entry("guardrail_verify", "prod",    "2026-03-05T09:00:00Z"),
    ])

    # ── CodePilot (prod, moderate risk) ──────────────────────────────────
    # Developer tool — fast iteration, lighter compliance burden.
    push("proj_codepilot", [
        entry("context_compile",  "dev",     "2025-12-15T10:00:00Z"),
        entry("security_scan",    "dev",     "2025-12-18T14:00:00Z"),
        entry("mcp_analysis",     "dev",     "2025-12-20T10:00:00Z"),
        entry("guardrail_verify", "dev",     "2025-12-22T11:00:00Z"),
        entry("workflow_analysis","dev",     "2025-12-24T10:00:00Z"),
        entry("context_compile",  "preprod", "2026-01-04T10:00:00Z"),
        entry("security_scan",    "preprod", "2026-01-07T14:00:00Z"),
        entry("attack_surface",   "preprod", "2026-01-10T15:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-01-14T14:00:00Z"),
        entry("compliance_check", "preprod", "2026-01-18T13:00:00Z"),
        entry("context_compile",  "prod",    "2026-02-03T10:00:00Z"),
        entry("security_scan",    "prod",    "2026-02-07T09:00:00Z"),
        entry("model_drift_check","prod",    "2026-02-12T08:00:00Z"),
        entry("security_scan",    "prod",    "2026-02-18T09:00:00Z"),
        entry("guardrail_verify", "prod",    "2026-02-24T11:00:00Z"),
        entry("security_scan",    "prod",    "2026-03-02T09:00:00Z"),
        entry("model_drift_check","prod",    "2026-03-05T08:00:00Z"),
    ])

    # ── PriceOracle (preprod, mission_critical) ───────────────────────────
    # Still hardening — extra compliance runs after failed dev eval.
    push("proj_priceoracle", [
        entry("context_compile",  "dev",     "2025-12-25T10:00:00Z"),
        entry("security_scan",    "dev",     "2025-12-28T14:00:00Z"),
        entry("security_scan",    "dev",     "2026-01-05T09:00:00Z", success=False),  # triggered re-run
        entry("security_scan",    "dev",     "2026-01-06T10:00:00Z"),
        entry("attack_surface",   "dev",     "2026-01-08T15:00:00Z"),
        entry("rai_evaluation",   "dev",     "2026-01-10T14:00:00Z", 0.18),
        entry("compliance_check", "dev",     "2026-01-12T13:00:00Z"),
        entry("context_compile",  "preprod", "2026-01-14T10:00:00Z"),
        entry("security_scan",    "preprod", "2026-01-17T14:00:00Z"),
        entry("mass_scan",        "preprod", "2026-01-20T10:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-01-24T14:00:00Z", 0.25),
        entry("compliance_check", "preprod", "2026-01-28T13:00:00Z", 0.15),
        entry("attack_surface",   "preprod", "2026-02-01T15:00:00Z"),
        entry("security_scan",    "preprod", "2026-02-08T09:00:00Z"),
        entry("workflow_analysis","preprod", "2026-02-13T14:00:00Z"),
        entry("security_scan",    "preprod", "2026-02-20T09:00:00Z"),
        entry("compliance_check", "preprod", "2026-02-27T13:00:00Z"),
        entry("security_review",  "preprod", "2026-03-01T10:00:00Z", 0.20),
    ])

    # ── Sentinel (preprod, mission_critical) ─────────────────────────────
    # RAI-heavy — safety AI requires deep evaluations.
    push("proj_sentinel", [
        entry("context_compile",  "dev",     "2026-01-04T10:00:00Z"),
        entry("security_scan",    "dev",     "2026-01-07T14:00:00Z"),
        entry("rai_evaluation",   "dev",     "2026-01-10T14:00:00Z", 0.30),
        entry("workflow_analysis","dev",     "2026-01-12T10:00:00Z"),
        entry("guardrail_verify", "dev",     "2026-01-15T11:00:00Z"),
        entry("mcp_analysis",     "dev",     "2026-01-17T10:00:00Z"),
        entry("context_compile",  "preprod", "2026-01-19T10:00:00Z"),
        entry("security_scan",    "preprod", "2026-01-22T14:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-01-26T14:00:00Z", 0.40),
        entry("rai_evaluation",   "preprod", "2026-01-30T14:00:00Z", 0.35),  # re-run after feedback
        entry("attack_surface",   "preprod", "2026-02-02T15:00:00Z"),
        entry("compliance_check", "preprod", "2026-02-06T13:00:00Z", 0.22),
        entry("mass_scan",        "preprod", "2026-02-10T10:00:00Z"),
        entry("security_review",  "preprod", "2026-02-14T10:00:00Z", 0.25),
        entry("rai_evaluation",   "preprod", "2026-02-20T14:00:00Z", 0.18),
        entry("guardrail_verify", "preprod", "2026-02-26T11:00:00Z"),
        entry("compliance_check", "preprod", "2026-03-03T13:00:00Z"),
    ])

    # ── MediAssist (preprod, mission_critical) ────────────────────────────
    # Medical AI — highest compliance bar, many re-runs.
    push("proj_mediassist", [
        entry("context_compile",  "dev",     "2026-01-04T10:00:00Z"),
        entry("security_scan",    "dev",     "2026-01-07T14:00:00Z"),
        entry("rai_evaluation",   "dev",     "2026-01-10T14:00:00Z", 0.35),
        entry("compliance_check", "dev",     "2026-01-13T13:00:00Z", 0.28),
        entry("workflow_analysis","dev",     "2026-01-15T10:00:00Z"),
        entry("guardrail_verify", "dev",     "2026-01-17T11:00:00Z"),
        entry("context_compile",  "preprod", "2026-01-19T10:00:00Z"),  # actually was preprod start
        entry("security_scan",    "preprod", "2026-01-14T14:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-01-18T14:00:00Z", 0.42),
        entry("compliance_check", "preprod", "2026-01-22T13:00:00Z", 0.30),
        entry("mass_scan",        "preprod", "2026-01-26T10:00:00Z"),
        entry("attack_surface",   "preprod", "2026-01-29T15:00:00Z"),
        entry("security_review",  "preprod", "2026-02-02T10:00:00Z", 0.38),
        entry("rai_evaluation",   "preprod", "2026-02-07T14:00:00Z", 0.28),  # post-rejection re-eval
        entry("compliance_check", "preprod", "2026-02-11T13:00:00Z", 0.22),
        entry("guardrail_verify", "preprod", "2026-02-15T11:00:00Z"),
        entry("security_scan",    "preprod", "2026-02-19T14:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-02-24T14:00:00Z", 0.20),
        entry("compliance_check", "preprod", "2026-03-01T13:00:00Z", 0.18),
        entry("security_review",  "preprod", "2026-03-04T10:00:00Z", 0.15),
    ])

    # ── NexusLLM (preprod, high risk) ────────────────────────────────────
    # Enterprise LLM — lots of workflow + MCP analysis.
    push("proj_nexusllm", [
        entry("context_compile",  "dev",     "2026-01-14T10:00:00Z"),
        entry("security_scan",    "dev",     "2026-01-17T14:00:00Z"),
        entry("mcp_analysis",     "dev",     "2026-01-19T10:00:00Z"),
        entry("workflow_analysis","dev",     "2026-01-21T10:00:00Z"),
        entry("attack_surface",   "dev",     "2026-01-23T15:00:00Z"),
        entry("rai_evaluation",   "dev",     "2026-01-26T14:00:00Z", 0.20),
        entry("guardrail_verify", "dev",     "2026-01-28T11:00:00Z"),
        entry("context_compile",  "preprod", "2026-02-13T10:00:00Z"),
        entry("security_scan",    "preprod", "2026-02-15T14:00:00Z"),
        entry("mcp_analysis",     "preprod", "2026-02-17T10:00:00Z"),
        entry("attack_surface",   "preprod", "2026-02-19T15:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-02-21T14:00:00Z", 0.30),
        entry("workflow_analysis","preprod", "2026-02-23T10:00:00Z"),
        entry("compliance_check", "preprod", "2026-02-25T13:00:00Z", 0.18),
        entry("mass_scan",        "preprod", "2026-02-27T10:00:00Z"),
        entry("security_review",  "preprod", "2026-03-01T10:00:00Z", 0.22),
        entry("guardrail_verify", "preprod", "2026-03-03T11:00:00Z"),
    ])

    # ── DataOps Classifier (prod, high risk) ─────────────────────────────
    # Fast pipeline — promoted through all stages in ~6 weeks.
    push("proj_dataops", [
        entry("context_compile",  "dev",     "2026-02-13T10:00:00Z"),
        entry("security_scan",    "dev",     "2026-02-15T14:00:00Z"),
        entry("guardrail_verify", "dev",     "2026-02-17T11:00:00Z"),
        entry("workflow_analysis","dev",     "2026-02-19T10:00:00Z"),
        entry("rai_evaluation",   "dev",     "2026-02-21T14:00:00Z"),
        entry("compliance_check", "dev",     "2026-02-23T13:00:00Z"),
        entry("context_compile",  "preprod", "2026-02-23T10:00:00Z"),
        entry("security_scan",    "preprod", "2026-02-25T14:00:00Z"),
        entry("attack_surface",   "preprod", "2026-02-27T15:00:00Z"),
        entry("rai_evaluation",   "preprod", "2026-03-01T14:00:00Z"),
        entry("compliance_check", "preprod", "2026-03-03T13:00:00Z"),
        entry("context_compile",  "prod",    "2026-03-05T10:00:00Z"),
        entry("security_scan",    "prod",    "2026-03-05T14:00:00Z"),
        entry("guardrail_verify", "prod",    "2026-03-05T16:00:00Z"),
    ])

    # ── RiskCopilot (dev, high risk) ─────────────────────────────────────
    # Newest project — just starting the hardening process.
    push("proj_riskcopilot", [
        entry("context_compile",  "dev",     "2026-01-29T10:00:00Z"),
        entry("security_scan",    "dev",     "2026-02-01T14:00:00Z"),
        entry("mcp_analysis",     "dev",     "2026-02-03T10:00:00Z"),
        entry("security_scan",    "dev",     "2026-02-07T14:00:00Z"),
        entry("workflow_analysis","dev",     "2026-02-10T10:00:00Z"),
        entry("rai_evaluation",   "dev",     "2026-02-14T14:00:00Z"),
        entry("guardrail_verify", "dev",     "2026-02-19T11:00:00Z"),
        entry("compliance_check", "dev",     "2026-02-24T13:00:00Z"),
        entry("security_scan",    "dev",     "2026-03-01T14:00:00Z"),
        entry("attack_surface",   "dev",     "2026-03-04T15:00:00Z"),
    ])

    print()
    print("  Done — cost totals now visible on each project overview and dashboard.")
    print()
    print("  Cost is derived from:")
    print("    • AI agent workflow runs (security_scan, rai_evaluation, compliance_check, …)")
    print("    • Model pricing (opus > sonnet > haiku)")
    print("    • Accumulated across all environments (dev + preprod + prod)")


if __name__ == "__main__":
    main()
