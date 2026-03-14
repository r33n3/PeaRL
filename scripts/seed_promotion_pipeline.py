"""
Seed promotion pipeline data:
  1. Run gate evaluations for all non-prod projects (populates readiness + blockers)
  2. Insert promotion history for each project's journey through the pipeline

Historical timeline (approximate, matching seed_demo_projects.py dates):
  FraudShield  sandbox→dev (d90), dev→preprod (d70), preprod→prod (d40)
  CodePilot    sandbox→dev (d80), dev→preprod (d60), preprod→prod (d30)
  PriceOracle  sandbox→dev (d70), dev→preprod (d50)       [still in preprod]
  Sentinel     sandbox→dev (d60), dev→preprod (d45)       [still in preprod]
  MediAssist   sandbox→dev (d60), dev→preprod (d50)       [still in preprod]
  NexusLLM     sandbox→dev (d50), dev→preprod (d20)       [still in preprod]
  DataOps      sandbox→dev (d20), dev→preprod (d10), preprod→prod (today/eve)
  RiskCopilot  sandbox→dev (d35)                          [still in dev]
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from pearl.db.models.promotion import PromotionEvaluationRow, PromotionHistoryRow

API = "http://localhost:8080/api/v1"
DB_URL = "postgresql+asyncpg://pearl:pearl@localhost:5432/pearl"

# ISO timestamps matching the project narrative
T = {
    "d90": "2025-12-05T10:00:00+00:00",
    "d80": "2025-12-15T10:00:00+00:00",
    "d70": "2025-12-25T10:00:00+00:00",
    "d60": "2026-01-04T10:00:00+00:00",
    "d50": "2026-01-14T10:00:00+00:00",
    "d55": "2026-01-09T10:00:00+00:00",
    "d45": "2026-01-19T10:00:00+00:00",
    "d40": "2026-01-24T10:00:00+00:00",
    "d35": "2026-01-29T10:00:00+00:00",
    "d30": "2026-02-03T10:00:00+00:00",
    "d20": "2026-02-13T10:00:00+00:00",
    "d10": "2026-02-23T10:00:00+00:00",
    "eve": "2026-03-05T17:00:00+00:00",
}


def ts(key: str) -> datetime:
    return datetime.fromisoformat(T[key])


def uid(prefix: str) -> str:
    return f"{prefix}{uuid4().hex[:16]}"


# ── Rule results templates ──────────────────────────────────────────────────

def _passed_rules_sandbox_dev():
    """Minimal passing rule set for sandbox→dev (gate has ~7 rules)."""
    return [
        {"rule_id": "rule_project_registered", "rule_type": "project_registered",
         "result": "pass", "message": "Project is registered"},
        {"rule_id": "rule_no_hardcoded_secrets", "rule_type": "no_hardcoded_secrets",
         "result": "pass", "message": "No hardcoded secrets"},
        {"rule_id": "rule_critical_findings_zero", "rule_type": "critical_findings_zero",
         "result": "pass", "message": "0 critical findings", "details": {"count": 0, "finding_ids": []}},
        {"rule_id": "rule_no_prompt_injection", "rule_type": "no_prompt_injection",
         "result": "pass", "message": "0 prompt injection findings", "details": {"count": 0}},
        {"rule_id": "rule_no_pii_leakage", "rule_type": "no_pii_leakage",
         "result": "pass", "message": "0 PII leakage findings"},
        {"rule_id": "rule_guardrails_verified", "rule_type": "guardrails_verified",
         "result": "pass", "message": "Guardrails verified (0 findings)"},
        {"rule_id": "rule_fairness_hard_blocks_clear", "rule_type": "fairness_hard_blocks_clear",
         "result": "pass", "message": "No fairness hard blocks"},
    ]


def _passed_rules_dev_preprod(project_id: str, with_fail: list[str] | None = None):
    """
    Rule results for dev→preprod.
    Pass all 26 rules for fully passing projects.
    with_fail: list of rule_types that should show as failed (for partial results).
    """
    all_rules = [
        ("rule_project_registered", "project_registered", "Project is registered"),
        ("rule_org_baseline_attached", "org_baseline_attached", "Org baseline attached"),
        ("rule_app_spec_defined", "app_spec_defined", "Application spec defined"),
        ("rule_no_hardcoded_secrets", "no_hardcoded_secrets", "No hardcoded secrets"),
        ("rule_unit_tests_exist", "unit_tests_exist", "Unit test evidence on file"),
        ("rule_security_baseline_tests", "security_baseline_tests", "Security baseline tests passed"),
        ("rule_critical_findings_zero", "critical_findings_zero",
         "0 critical findings", {"count": 0, "finding_ids": []}),
        ("rule_data_classifications_documented", "data_classifications_documented",
         "Data classifications documented"),
        ("rule_iam_roles_defined", "iam_roles_defined", "IAM roles defined"),
        ("rule_high_findings_zero", "high_findings_zero",
         "0 high findings", {"count": 0}),
        ("rule_network_boundaries_declared", "network_boundaries_declared",
         "Network boundaries declared"),
        ("rule_integration_test_coverage", "integration_test_coverage",
         "Integration coverage 82.0% (threshold 60.0%)"),
        ("rule_security_review_approval", "security_review_approval",
         "Security review approved"),
        ("rule_fairness_case_defined", "fairness_case_defined", "Fairness case on file"),
        ("rule_mass_scan_completed", "mass_scan_completed", "MASS scan completed"),
        ("rule_no_prompt_injection", "no_prompt_injection",
         "0 prompt injection findings", {"count": 0}),
        ("rule_required_analyzers_completed", "required_analyzers_completed",
         "All required analyzers completed",
         {"completed": ["context", "mcp", "workflow", "attack_surface"], "missing": []}),
        ("rule_fairness_requirements_met", "fairness_requirements_met",
         "Fairness requirements met"),
        ("rule_guardrails_verified", "guardrails_verified",
         "Guardrails verified (0 findings)"),
        ("rule_no_pii_leakage", "no_pii_leakage", "0 PII leakage findings"),
        ("rule_fairness_attestation_signed", "fairness_attestation_signed",
         "Fairness attestation signed"),
        ("rule_fairness_hard_blocks_clear", "fairness_hard_blocks_clear",
         "No fairness hard blocks"),
        ("rule_rai_eval_completed", "rai_eval_completed", "RAI evaluation on record"),
        ("rule_compliance_score_threshold", "compliance_score_threshold",
         "Compliance score 91.0% (threshold 80.0%)"),
        ("rule_security_review_clear", "security_review_clear",
         "Security review: 0 open findings"),
        ("rule_guardrail_coverage", "guardrail_coverage",
         "Guardrail coverage adequate"),
    ]
    with_fail = with_fail or []
    results = []
    for entry in all_rules:
        rid, rtype, msg = entry[0], entry[1], entry[2]
        details = entry[3] if len(entry) > 3 else None
        if rtype in with_fail:
            fail_msg = {
                "high_findings_zero": "2 high findings open — must be zero before preprod",
                "unit_tests_exist": "No unit test evidence found",
                "security_review_approval": "No security review approval",
            }.get(rtype, f"Rule failed: {rtype}")
            r = {"rule_id": rid, "rule_type": rtype, "result": "fail", "message": fail_msg}
        else:
            r = {"rule_id": rid, "rule_type": rtype, "result": "pass", "message": msg}
            if details:
                r["details"] = details
        results.append(r)
    return results


def _passed_rules_preprod_prod(project_id: str, with_fail: list[str] | None = None):
    """29-rule preprod→prod gate. Pass all unless with_fail specified."""
    base_rules = [
        ("rule_project_registered", "project_registered", "Project is registered"),
        ("rule_org_baseline_attached", "org_baseline_attached", "Org baseline attached"),
        ("rule_app_spec_defined", "app_spec_defined", "Application spec defined"),
        ("rule_no_hardcoded_secrets", "no_hardcoded_secrets", "No hardcoded secrets"),
        ("rule_critical_findings_zero", "critical_findings_zero",
         "0 critical findings", {"count": 0, "finding_ids": []}),
        ("rule_high_findings_zero", "high_findings_zero",
         "0 high findings", {"count": 0}),
        ("rule_security_review_approval", "security_review_approval",
         "Security review approved"),
        ("rule_fairness_case_defined", "fairness_case_defined", "Fairness case on file"),
        ("rule_mass_scan_completed", "mass_scan_completed", "MASS scan completed"),
        ("rule_no_prompt_injection", "no_prompt_injection",
         "0 prompt injection findings", {"count": 0}),
        ("rule_fairness_requirements_met", "fairness_requirements_met",
         "Fairness requirements met"),
        ("rule_guardrails_verified", "guardrails_verified", "Guardrails verified (0 findings)"),
        ("rule_no_pii_leakage", "no_pii_leakage", "0 PII leakage findings"),
        ("rule_fairness_attestation_signed", "fairness_attestation_signed",
         "Fairness attestation signed"),
        ("rule_fairness_hard_blocks_clear", "fairness_hard_blocks_clear",
         "No fairness hard blocks"),
        ("rule_rai_eval_completed", "rai_eval_completed", "RAI evaluation on record"),
        ("rule_compliance_score_threshold", "compliance_score_threshold",
         "Compliance score 94.0% (threshold 80.0%)"),
        ("rule_security_review_clear", "security_review_clear",
         "Security review: 0 open findings"),
        ("rule_guardrail_coverage", "guardrail_coverage", "Guardrail coverage adequate"),
        ("rule_required_analyzers_completed", "required_analyzers_completed",
         "All required analyzers completed",
         {"completed": ["context", "mcp", "workflow", "attack_surface"], "missing": []}),
        ("rule_integration_test_coverage", "integration_test_coverage",
         "Integration coverage 88.0% (threshold 60.0%)"),
        ("rule_data_classifications_documented", "data_classifications_documented",
         "Data classifications documented"),
        ("rule_iam_roles_defined", "iam_roles_defined", "IAM roles defined"),
        ("rule_network_boundaries_declared", "network_boundaries_declared",
         "Network boundaries declared"),
        ("rule_unit_tests_exist", "unit_tests_exist", "Unit test evidence on file"),
        ("rule_security_baseline_tests", "security_baseline_tests",
         "Security baseline tests passed"),
        # Additional prod-only rules (padding to ~29)
        ("rule_model_card_on_file", "model_card_on_file", "Model card on file"),
        ("rule_incident_response_plan", "incident_response_plan",
         "Incident response plan attached"),
        ("rule_sla_defined", "sla_defined", "SLA defined and approved"),
    ]
    with_fail = with_fail or []
    results = []
    for entry in base_rules:
        rid, rtype, msg = entry[0], entry[1], entry[2]
        details = entry[3] if len(entry) > 3 else None
        if rtype in with_fail:
            fail_msgs = {
                "high_findings_zero": "1 high finding open — must be zero for prod",
                "rai_eval_completed": "No RAI evaluation on record",
                "compliance_score_threshold": "Compliance score 71% below threshold 80%",
            }
            r = {"rule_id": rid, "rule_type": rtype, "result": "fail",
                 "message": fail_msgs.get(rtype, f"Rule failed: {rtype}")}
        else:
            r = {"rule_id": rid, "rule_type": rtype, "result": "pass", "message": msg}
            if details:
                r["details"] = details
        results.append(r)
    return results


# ── DB insertion ────────────────────────────────────────────────────────────

async def insert_eval(session: AsyncSession, *, evaluation_id, project_id,
                      gate_id, source_env, target_env, rule_results,
                      promoted_at: datetime, blockers=None) -> str:
    passed = sum(1 for r in rule_results if r["result"] == "pass")
    failed = sum(1 for r in rule_results if r["result"] == "fail")
    total = len(rule_results)
    pct = round(passed / total * 100, 1) if total else 0.0
    status = "passed" if failed == 0 else ("partial" if passed > 0 else "failed")

    row = PromotionEvaluationRow(
        evaluation_id=evaluation_id,
        project_id=project_id,
        gate_id=gate_id,
        source_environment=source_env,
        target_environment=target_env,
        status=status,
        rule_results=rule_results,
        passed_count=passed,
        failed_count=failed,
        skipped_count=0,
        total_count=total,
        progress_pct=pct,
        blockers=blockers,
        evaluated_at=promoted_at,
        trace_id=uid("trc_"),
    )
    session.add(row)
    return evaluation_id


async def insert_history(session: AsyncSession, *, history_id, project_id,
                         source_env, target_env, evaluation_id,
                         promoted_by: str, promoted_at: datetime,
                         conditions: list[str] | None = None):
    row = PromotionHistoryRow(
        history_id=history_id,
        project_id=project_id,
        source_environment=source_env,
        target_environment=target_env,
        evaluation_id=evaluation_id,
        promoted_by=promoted_by,
        promoted_at=promoted_at,
        details={
            "auto_approved": False,
            "approval_request_id": uid("appr_"),
            **({"conditions": conditions} if conditions else {}),
        },
    )
    session.add(row)


# ── Per-project history seeding ─────────────────────────────────────────────

async def seed_fraudshield(session: AsyncSession):
    pid = "proj_fraudshield"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d90"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="fraud-eng-ci@internal",
                         promoted_at=ts("d90"))

    eid2 = uid("eval_")
    await insert_eval(session, evaluation_id=eid2, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(pid),
                      promoted_at=ts("d70"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="dev", target_env="preprod",
                         evaluation_id=eid2, promoted_by="fraud-eng-ci@internal",
                         promoted_at=ts("d70"))

    eid3 = uid("eval_")
    await insert_eval(session, evaluation_id=eid3, project_id=pid,
                      gate_id="gate_preprod_to_prod", source_env="preprod",
                      target_env="prod",
                      rule_results=_passed_rules_preprod_prod(pid),
                      promoted_at=ts("d40"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="preprod", target_env="prod",
                         evaluation_id=eid3, promoted_by="ciso@internal",
                         promoted_at=ts("d40"))
    print(f"  ✓  {pid}  (sandbox→dev→preprod→prod)")


async def seed_codepilot(session: AsyncSession):
    pid = "proj_codepilot"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d80"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="platform-ci@internal",
                         promoted_at=ts("d80"))

    eid2 = uid("eval_")
    await insert_eval(session, evaluation_id=eid2, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(pid),
                      promoted_at=ts("d60"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="dev", target_env="preprod",
                         evaluation_id=eid2, promoted_by="platform-ci@internal",
                         promoted_at=ts("d60"))

    eid3 = uid("eval_")
    await insert_eval(session, evaluation_id=eid3, project_id=pid,
                      gate_id="gate_preprod_to_prod", source_env="preprod",
                      target_env="prod",
                      rule_results=_passed_rules_preprod_prod(pid),
                      promoted_at=ts("d30"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="preprod", target_env="prod",
                         evaluation_id=eid3, promoted_by="ciso@internal",
                         promoted_at=ts("d30"))
    print(f"  ✓  {pid}  (sandbox→dev→preprod→prod)")


async def seed_priceoracle(session: AsyncSession):
    pid = "proj_priceoracle"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d70"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="pricing-ci@internal",
                         promoted_at=ts("d70"))

    # dev→preprod had a partial run first (high findings open), then passed
    eid2a = uid("eval_")
    await insert_eval(session, evaluation_id=eid2a, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(
                          pid, with_fail=["high_findings_zero"]),
                      promoted_at=ts("d55"),
                      blockers=["2 high findings open — must be zero before preprod"])
    # (no history record for this — it was a failed eval, not a promotion)

    eid2b = uid("eval_")
    await insert_eval(session, evaluation_id=eid2b, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(pid),
                      promoted_at=ts("d50"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="dev", target_env="preprod",
                         evaluation_id=eid2b, promoted_by="pricing-ci@internal",
                         promoted_at=ts("d50"))
    print(f"  ✓  {pid}  (sandbox→dev→preprod, with 1 failed eval in dev)")


async def seed_sentinel(session: AsyncSession):
    pid = "proj_sentinel"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d60"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="safety-ci@internal",
                         promoted_at=ts("d60"))

    eid2 = uid("eval_")
    await insert_eval(session, evaluation_id=eid2, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(pid),
                      promoted_at=ts("d45"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="dev", target_env="preprod",
                         evaluation_id=eid2, promoted_by="safety-ci@internal",
                         promoted_at=ts("d45"))
    print(f"  ✓  {pid}  (sandbox→dev→preprod)")


async def seed_mediassist(session: AsyncSession):
    pid = "proj_mediassist"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d60"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="medai-ci@internal",
                         promoted_at=ts("d60"))

    eid2 = uid("eval_")
    await insert_eval(session, evaluation_id=eid2, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(pid),
                      promoted_at=ts("d50"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="dev", target_env="preprod",
                         evaluation_id=eid2, promoted_by="medai-ci@internal",
                         promoted_at=ts("d50"))
    print(f"  ✓  {pid}  (sandbox→dev→preprod)")


async def seed_nexusllm(session: AsyncSession):
    pid = "proj_nexusllm"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d50"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="enterprise-ai-ci@internal",
                         promoted_at=ts("d50"))

    eid2 = uid("eval_")
    await insert_eval(session, evaluation_id=eid2, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(pid),
                      promoted_at=ts("d20"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="dev", target_env="preprod",
                         evaluation_id=eid2, promoted_by="enterprise-ai-ci@internal",
                         promoted_at=ts("d20"))
    print(f"  ✓  {pid}  (sandbox→dev→preprod)")


async def seed_dataops(session: AsyncSession):
    pid = "proj_dataops"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d20"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="data-engineering-ci@internal",
                         promoted_at=ts("d20"))

    eid2 = uid("eval_")
    await insert_eval(session, evaluation_id=eid2, project_id=pid,
                      gate_id="gate_dev_to_preprod", source_env="dev",
                      target_env="preprod",
                      rule_results=_passed_rules_dev_preprod(pid),
                      promoted_at=ts("d10"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="dev", target_env="preprod",
                         evaluation_id=eid2, promoted_by="security-lead@internal",
                         promoted_at=ts("d10"))

    eid3 = uid("eval_")
    await insert_eval(session, evaluation_id=eid3, project_id=pid,
                      gate_id="gate_preprod_to_prod", source_env="preprod",
                      target_env="prod",
                      rule_results=_passed_rules_preprod_prod(pid),
                      promoted_at=ts("eve"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="preprod", target_env="prod",
                         evaluation_id=eid3, promoted_by="ciso@internal",
                         promoted_at=ts("eve"),
                         conditions=[
                             "Routing audit trail must be implemented within 30 days",
                             "Model card to be filed in the registry within 14 days",
                             "Confidence score exposure required before next model update",
                         ])
    print(f"  ✓  {pid}  (sandbox→dev→preprod→prod, with conditions)")


async def seed_riskcopilot(session: AsyncSession):
    pid = "proj_riskcopilot"

    eid1 = uid("eval_")
    await insert_eval(session, evaluation_id=eid1, project_id=pid,
                      gate_id="gate_sandbox_to_dev", source_env="sandbox",
                      target_env="dev",
                      rule_results=_passed_rules_sandbox_dev(),
                      promoted_at=ts("d35"))
    await insert_history(session, history_id=uid("promhist_"), project_id=pid,
                         source_env="sandbox", target_env="dev",
                         evaluation_id=eid1, promoted_by="audit-risk-ci@internal",
                         promoted_at=ts("d35"))
    print(f"  ✓  {pid}  (sandbox→dev)")


# ── Live evaluations (current state) ──────────────────────────────────────

def run_evaluate(project_id: str, label: str):
    """Call the evaluate endpoint to populate current readiness data."""
    c = httpx.Client(base_url=API, timeout=30)
    r = c.post(f"/projects/{project_id}/promotions/evaluate")
    if r.status_code == 200:
        d = r.json()
        blockers = d.get("blockers") or []
        print(f"  ✓  {project_id:<22}  {label}  "
              f"[{d['status']} {d['progress_pct']:.0f}%  "
              f"{d['passed_count']}✓ {d['failed_count']}✗]"
              + (f"  {len(blockers)} blocker(s)" if blockers else ""))
    else:
        print(f"  ✗  {project_id:<22}  {r.status_code}: {r.text[:120]}")


# ── Main ───────────────────────────────────────────────────────────────────

async def main():
    print()
    print("  PeaRL Promotion Pipeline Seed")
    print()

    # 1. Seed historical promotion records via ORM
    print("── Historical promotion records (direct DB insert) ──")
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with session.begin():
            await seed_fraudshield(session)
            await seed_codepilot(session)
            await seed_priceoracle(session)
            await seed_sentinel(session)
            await seed_mediassist(session)
            await seed_nexusllm(session)
            await seed_dataops(session)
            await seed_riskcopilot(session)

    await engine.dispose()
    print()

    # 2. Run live evaluations for non-prod projects (populates readiness + blockers)
    print("── Current gate evaluations (API) ──")
    run_evaluate("proj_riskcopilot", "dev→preprod")
    run_evaluate("proj_priceoracle", "preprod→prod")
    run_evaluate("proj_sentinel",    "preprod→prod")
    run_evaluate("proj_mediassist",  "preprod→prod")
    run_evaluate("proj_nexusllm",    "preprod→prod")

    print()
    print("  Done — refresh http://localhost:5177")
    print("  Each project's Promotion tab now shows pipeline history and current gate status.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
