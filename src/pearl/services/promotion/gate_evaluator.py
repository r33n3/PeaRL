"""Gate evaluation engine — checks project readiness for environment promotion."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.finding import FindingRow
from pearl.errors.exceptions import ValidationError
from pearl.models.enums import (
    GateEvaluationStatus,
    GateRuleResult,
    GateRuleType,
)
from pearl.models.promotion import (
    GateRuleDefinition,
    PromotionEvaluation,
    RuleEvaluationResult,
)
from pearl.repositories.app_spec_repo import AppSpecRepository
from pearl.repositories.approval_repo import ApprovalRequestRepository
from pearl.repositories.compiled_package_repo import CompiledPackageRepository
from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
from pearl.repositories.exception_repo import ExceptionRepository
from pearl.repositories.fairness_repo import (
    ContextReceiptRepository,
    EvidencePackageRepository,
    FairnessCaseRepository,
    FairnessExceptionRepository,
    FairnessRequirementsSpecRepository,
    MonitoringSignalRepository,
)
from pearl.repositories.finding_repo import FindingRepository
from pearl.repositories.org_baseline_repo import OrgBaselineRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.pipeline_repo import PromotionPipelineRepository
from pearl.repositories.promotion_repo import (
    PromotionEvaluationRepository,
    PromotionGateRepository,
)
from pearl.repositories.report_repo import ReportRepository
from pearl.services.id_generator import generate_id


async def next_environment(current: str, session: AsyncSession) -> str | None:
    """Get the next environment in the promotion chain from the default pipeline."""
    pipeline = await PromotionPipelineRepository(session).get_default()
    if not pipeline:
        return None
    stages = sorted(pipeline.stages, key=lambda s: s["order"])
    keys = [s["key"] for s in stages]
    try:
        idx = keys.index(current)
        return keys[idx + 1] if idx < len(keys) - 1 else None
    except ValueError:
        return None


async def evaluate_promotion(
    project_id: str,
    target_environment: str | None = None,
    trace_id: str | None = None,
    session: AsyncSession | None = None,
) -> PromotionEvaluation:
    """Evaluate project readiness for promotion to the next environment.

    1. Load project + current environment
    2. Determine target environment (next in chain)
    3. Load gate rules for the transition
    4. Evaluate each rule
    5. Persist evaluation
    6. Return result
    """
    # Load project
    project_repo = ProjectRepository(session)
    project = await project_repo.get(project_id)
    if not project:
        raise ValidationError(f"Project '{project_id}' not found")

    # Determine current environment
    env_repo = EnvironmentProfileRepository(session)
    env_profile = await env_repo.get_by_project(project_id)
    current_env = env_profile.environment if env_profile else "sandbox"

    # Determine target
    if not target_environment:
        target_environment = await next_environment(current_env, session)
    if not target_environment:
        raise ValidationError(f"No promotion target from '{current_env}'")

    # Load gate rules
    gate_repo = PromotionGateRepository(session)
    gate = await gate_repo.get_for_transition(current_env, target_environment, project_id)
    if not gate:
        raise ValidationError(
            f"No promotion gate defined for {current_env} -> {target_environment}"
        )

    # Build evaluation context: load all needed data
    ctx = await _build_eval_context(project_id, project, session)

    # Evaluate each rule
    rule_results = []
    for rule_def in _parse_rules(gate.rules):
        result = _evaluate_rule(rule_def, ctx)
        rule_results.append(result)

    # Calculate summary
    passed = sum(1 for r in rule_results if r.result == GateRuleResult.PASS)
    failed = sum(1 for r in rule_results if r.result == GateRuleResult.FAIL)
    skipped = sum(1 for r in rule_results if r.result == GateRuleResult.SKIP)
    total = len(rule_results)
    progress = round((passed / total * 100) if total > 0 else 0, 1)

    blockers = [r.message for r in rule_results if r.result == GateRuleResult.FAIL]

    if failed == 0:
        status = GateEvaluationStatus.PASSED
    elif passed > 0:
        status = GateEvaluationStatus.PARTIAL
    else:
        status = GateEvaluationStatus.FAILED

    evaluation = PromotionEvaluation(
        evaluation_id=generate_id("eval_"),
        project_id=project_id,
        gate_id=gate.gate_id,
        source_environment=current_env,
        target_environment=target_environment,
        status=status,
        rule_results=rule_results,
        passed_count=passed,
        failed_count=failed,
        skipped_count=skipped,
        total_count=total,
        progress_pct=progress,
        blockers=blockers if blockers else None,
        evaluated_at=datetime.now(timezone.utc),
        trace_id=trace_id,
    )

    # Persist evaluation
    eval_repo = PromotionEvaluationRepository(session)
    await eval_repo.create(
        evaluation_id=evaluation.evaluation_id,
        project_id=project_id,
        gate_id=gate.gate_id,
        source_environment=current_env,
        target_environment=target_environment,
        status=status.value,
        rule_results=[r.model_dump(mode="json") for r in rule_results],
        passed_count=passed,
        failed_count=failed,
        skipped_count=skipped,
        total_count=total,
        progress_pct=progress,
        blockers=blockers if blockers else None,
        trace_id=trace_id,
        evaluated_at=evaluation.evaluated_at,
    )

    return evaluation


class _EvalContext:
    """Container for all data needed during rule evaluation."""

    def __init__(self):
        self.project = None
        self.ai_enabled = False
        self.has_baseline = False
        self.has_app_spec = False
        self.has_env_profile = False
        self.has_compiled_package = False
        self.findings_by_severity = {}
        self.findings_by_category = {}
        self.findings_by_source = {}
        self.open_findings = []
        self.has_approval = {}
        self.active_exceptions = []
        self.has_report = {}
        # Fairness context
        self.has_fairness_case = False
        self.has_frs = False
        self.frs_requirements = []
        self.evidence_packages = []
        self.has_signed_attestation = False
        self.fairness_exceptions = []
        self.monitoring_signals = []
        self.has_context_receipt = False
        # App spec data
        self.app_spec_data = {}
        # Scan targets
        self.scan_targets = []
        self.mass_scan_targets = []
        self.has_mass_scan_target = False
        self.mass_scan_completed = False
        # Scanning integration context
        self.completed_analyzers: list[str] = []
        self.pearl_scan_findings: list = []
        self.security_review_findings: list = []
        self.compliance_score: float | None = None
        self.compliance_assessment = None
        # AIUC-1 baseline defaults (category → sub-control → bool | None)
        self.baseline_defaults = {}


async def _build_eval_context(
    project_id: str, project, session: AsyncSession
) -> _EvalContext:
    ctx = _EvalContext()
    ctx.project = project
    ctx.ai_enabled = project.ai_enabled

    # Check baseline
    baseline_repo = OrgBaselineRepository(session)
    baseline = await baseline_repo.get_by_project(project_id)
    ctx.has_baseline = baseline is not None
    ctx.baseline_defaults = (baseline.defaults or {}) if baseline else {}

    # Check app spec
    app_spec_repo = AppSpecRepository(session)
    app_spec = await app_spec_repo.get_by_project(project_id)
    ctx.has_app_spec = app_spec is not None
    if app_spec:
        ctx.app_spec_data = app_spec.full_spec or {}

    # Check env profile
    env_repo = EnvironmentProfileRepository(session)
    env_profile = await env_repo.get_by_project(project_id)
    ctx.has_env_profile = env_profile is not None

    # Check compiled package
    pkg_repo = CompiledPackageRepository(session)
    pkg = await pkg_repo.get_latest_by_project(project_id)
    ctx.has_compiled_package = pkg is not None

    # Load findings (open only)
    stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.status == "open",
    )
    result = await session.execute(stmt)
    all_findings = list(result.scalars().all())
    ctx.open_findings = all_findings

    for f in all_findings:
        sev = f.severity
        ctx.findings_by_severity.setdefault(sev, []).append(f)
        ctx.findings_by_category.setdefault(f.category, []).append(f)
        source = (f.source or {}).get("tool_type", "unknown")
        ctx.findings_by_source.setdefault(source, []).append(f)

    # Load approvals
    approval_repo = ApprovalRequestRepository(session)
    approvals = await approval_repo.list_by_project(project_id)
    for a in approvals:
        if a.status == "approved":
            ctx.has_approval[a.request_type] = True

    # Load exceptions
    exc_repo = ExceptionRepository(session)
    ctx.active_exceptions = await exc_repo.get_active_by_project(project_id)

    # Load reports
    report_repo = ReportRepository(session)
    reports = await report_repo.list_by_project(project_id)
    for r in reports:
        ctx.has_report[r.report_type] = True

    # Fairness data
    fc_repo = FairnessCaseRepository(session)
    fc = await fc_repo.get_by_project(project_id)
    ctx.has_fairness_case = fc is not None

    frs_repo = FairnessRequirementsSpecRepository(session)
    frs = await frs_repo.get_by_project(project_id)
    ctx.has_frs = frs is not None
    if frs:
        ctx.frs_requirements = frs.requirements or []

    ev_repo = EvidencePackageRepository(session)
    ctx.evidence_packages = await ev_repo.list_by_project(project_id)
    ctx.has_signed_attestation = any(
        e.attestation_status == "signed" for e in ctx.evidence_packages
    )

    fex_repo = FairnessExceptionRepository(session)
    ctx.fairness_exceptions = await fex_repo.get_active_by_project(project_id)

    # Load all monitoring signals (we'll check thresholds per-rule)
    from pearl.db.models.fairness import MonitoringSignalRow

    stmt2 = select(MonitoringSignalRow).where(MonitoringSignalRow.project_id == project_id)
    result2 = await session.execute(stmt2)
    ctx.monitoring_signals = list(result2.scalars().all())

    cr_repo = ContextReceiptRepository(session)
    receipts = await cr_repo.list_by_field("project_id", project_id)
    ctx.has_context_receipt = len(receipts) > 0

    # Load scan targets
    from pearl.repositories.scan_target_repo import ScanTargetRepository

    st_repo = ScanTargetRepository(session)
    ctx.scan_targets = await st_repo.list_by_project(project_id)
    ctx.mass_scan_targets = [st for st in ctx.scan_targets if st.tool_type == "mass"]
    ctx.has_mass_scan_target = len(ctx.mass_scan_targets) > 0
    ctx.mass_scan_completed = any(
        st.last_scan_status == "succeeded" for st in ctx.mass_scan_targets
    )

    # Scanning integration: pearl_scan findings and security review findings (open only)
    ctx.pearl_scan_findings = [
        f for f in all_findings
        if (f.source or {}).get("tool_name", "").startswith("pearl_scan")
    ]
    ctx.security_review_findings = [
        f for f in all_findings
        if (f.source or {}).get("tool_name") == "claude_security_review"
    ]

    # Load ALL pearl_scan findings (including closed completion markers) for analyzer tracking.
    # The open_findings query above filters to status=="open", but completion markers are
    # status=="closed" info-level findings created for 0-finding analyzers.
    all_scan_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
    )
    all_scan_result = await session.execute(all_scan_stmt)
    all_project_findings = list(all_scan_result.scalars().all())
    all_pearl_scan = [
        f for f in all_project_findings
        if (f.source or {}).get("tool_name", "").startswith("pearl_scan")
    ]

    # Determine which analyzers have completed from ALL pearl_scan findings
    analyzer_names_seen: set[str] = set()
    for f in all_pearl_scan:
        tool_name = (f.source or {}).get("tool_name", "")
        if tool_name.startswith("pearl_scan_"):
            analyzer_names_seen.add(tool_name.replace("pearl_scan_", ""))
    ctx.completed_analyzers = list(analyzer_names_seen)

    # Also count pearl_scan findings as MASS scan completed
    if all_pearl_scan and not ctx.mass_scan_completed:
        ctx.mass_scan_completed = True

    # Run compliance assessment if pearl_scan findings exist
    if ctx.pearl_scan_findings:
        try:
            from pearl.scanning.compliance.assessor import ComplianceAssessor
            from pearl.scanning.types import AttackCategory, ScanSeverity

            finding_dicts = []
            for f in ctx.pearl_scan_findings:
                full = f.full_data or {}
                cat_str = full.get("category", f.category)
                sev_str = full.get("severity", f.severity)
                try:
                    cat = AttackCategory(cat_str)
                except (ValueError, KeyError):
                    cat = cat_str
                try:
                    sev = ScanSeverity(sev_str)
                except (ValueError, KeyError):
                    sev = sev_str
                finding_dicts.append({"category": cat, "severity": sev, "id": f.finding_id})

            assessor = ComplianceAssessor()
            ctx.compliance_assessment = assessor.assess(finding_dicts)
            ctx.compliance_score = ctx.compliance_assessment.overall_compliance_score
        except Exception:
            pass

    return ctx


def _parse_rules(rules_data) -> list[GateRuleDefinition]:
    """Parse rules from gate JSON data into GateRuleDefinition objects."""
    if isinstance(rules_data, list):
        return [GateRuleDefinition(**r) if isinstance(r, dict) else r for r in rules_data]
    return []


def _evaluate_rule(rule: GateRuleDefinition, ctx: _EvalContext) -> RuleEvaluationResult:
    """Evaluate a single gate rule against the context."""
    # Skip AI-only rules if project is not AI-enabled
    if rule.ai_only and not ctx.ai_enabled:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            result=GateRuleResult.SKIP,
            message=f"Skipped: {rule.description} (not AI-enabled)",
        )

    evaluator = RULE_EVALUATORS.get(rule.rule_type)
    if not evaluator:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            result=GateRuleResult.SKIP,
            message=f"Unknown rule type: {rule.rule_type}",
        )

    try:
        passed, message, details = evaluator(rule, ctx)
        if not passed:
            # Check if an active exception covers this rule
            covering = next(
                (
                    e for e in ctx.active_exceptions
                    if rule.rule_type in ((getattr(e, "scope", None) or {}).get("controls") or [])
                ),
                None,
            )
            if covering:
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_type=rule.rule_type,
                    result=GateRuleResult.EXCEPTION,
                    message=f"Covered by active exception {covering.exception_id}: {message}",
                    exception_id=covering.exception_id,
                )
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            result=GateRuleResult.PASS if passed else GateRuleResult.FAIL,
            message=message,
            details=details,
        )
    except Exception as exc:
        return RuleEvaluationResult(
            rule_id=rule.rule_id,
            rule_type=rule.rule_type,
            result=GateRuleResult.FAIL,
            message=f"Evaluation error: {exc}",
        )


# ──────────────────────────────────────────────
# Rule evaluator functions
# Each returns (passed: bool, message: str, details: dict | None)
# ──────────────────────────────────────────────


def _eval_project_registered(rule, ctx):
    return ctx.project is not None, "Project is registered" if ctx.project else "Project not registered", None


def _eval_org_baseline_attached(rule, ctx):
    return ctx.has_baseline, "Org baseline attached" if ctx.has_baseline else "No org baseline attached", None


def _eval_app_spec_defined(rule, ctx):
    return ctx.has_app_spec, "Application spec defined" if ctx.has_app_spec else "No application spec defined", None


def _eval_no_hardcoded_secrets(rule, ctx):
    secret_findings = [f for f in ctx.open_findings if "secret" in (f.title or "").lower() or "hardcoded" in (f.title or "").lower()]
    passed = len(secret_findings) == 0
    return passed, f"No hardcoded secrets" if passed else f"{len(secret_findings)} hardcoded secret finding(s)", None


def _eval_unit_tests_exist(rule, ctx):
    # Check app spec for test declarations
    tests = ctx.app_spec_data.get("tests", {}) or ctx.app_spec_data.get("testing", {})
    if tests:
        return True, "Unit tests declared in app spec", None
    # Check evidence packages for test-related evidence
    test_evidence_types = {"ci_eval_report", "test_results", "bias_benchmark", "runtime_sample"}
    test_evidence = [
        e for e in ctx.evidence_packages
        if getattr(e, "evidence_type", None) in test_evidence_types
    ]
    if test_evidence:
        return True, f"Unit test evidence submitted ({len(test_evidence)} package(s))", None
    return False, "No unit test evidence found", None


def _eval_unit_test_coverage(rule, ctx):
    threshold = rule.threshold or 80
    # Would need actual coverage data; for now check if report exists
    return ctx.has_report.get("control_coverage", False), f"Coverage report exists (threshold: {threshold}%)" if ctx.has_report.get("control_coverage") else f"No coverage report (need {threshold}%)", None


def _eval_integration_test_coverage(rule, ctx):
    threshold = rule.threshold or 60
    return ctx.has_report.get("control_coverage", False), f"Integration coverage report exists (threshold: {threshold}%)" if ctx.has_report.get("control_coverage") else f"No integration coverage (need {threshold}%)", None


def _eval_security_baseline_tests(rule, ctx):
    return ctx.has_compiled_package, "Security baseline tests linked via compiled package" if ctx.has_compiled_package else "No compiled context package", None


def _eval_critical_findings_zero(rule, ctx):
    count = len(ctx.findings_by_severity.get("critical", []))
    return count == 0, f"0 critical findings" if count == 0 else f"{count} critical finding(s) open", {"count": count}


def _eval_high_findings_zero(rule, ctx):
    count = len(ctx.findings_by_severity.get("high", []))
    return count == 0, f"0 high findings" if count == 0 else f"{count} high finding(s) open", {"count": count}


def _eval_data_classifications_documented(rule, ctx):
    data = ctx.app_spec_data.get("data", {})
    classifications = data.get("data_classifications") or data.get("classifications")
    passed = bool(classifications)
    return passed, "Data classifications documented" if passed else "No data classifications in app spec", None


def _eval_iam_roles_defined(rule, ctx):
    iam = ctx.app_spec_data.get("iam", {})
    arch = ctx.app_spec_data.get("architecture", {})
    trust_boundaries = arch.get("trust_boundaries", []) if isinstance(arch, dict) else []
    passed = bool(iam) or bool(trust_boundaries)
    return passed, "IAM roles/trust boundaries defined" if passed else "No IAM roles defined", None


def _eval_network_boundaries_declared(rule, ctx):
    network = ctx.app_spec_data.get("network", {})
    arch = ctx.app_spec_data.get("architecture", {})
    trust_boundaries = arch.get("trust_boundaries", []) if isinstance(arch, dict) else []
    passed = bool(network) or bool(trust_boundaries)
    return passed, "Network boundaries declared" if passed else "No network boundaries declared", None


def _eval_all_controls_verified(rule, ctx):
    return ctx.has_compiled_package and ctx.has_report.get("control_coverage", False), "All controls verified" if ctx.has_compiled_package else "Controls not fully verified", None


def _eval_security_review_approval(rule, ctx):
    passed = ctx.has_approval.get("deployment_gate", False) or ctx.has_approval.get("auth_flow_change", False)
    return passed, "Security review approval on file" if passed else "No security review approval", None


def _eval_exec_sponsor_approval(rule, ctx):
    passed = ctx.has_approval.get("promotion_gate", False)
    return passed, "Executive sponsor approval on file" if passed else "No executive sponsor approval", None


def _eval_residual_risk_report(rule, ctx):
    passed = ctx.has_report.get("residual_risk", False)
    return passed, "Residual risk report generated" if passed else "No residual risk report", None


def _eval_read_only_autonomy(rule, ctx):
    env_profile = ctx.has_env_profile
    return env_profile, "Environment profile defines autonomy mode" if env_profile else "No environment profile to verify autonomy mode", None


# MASS-sourced AI security rules

def _eval_mass_scan_completed(rule, ctx):
    # Primary check: scan target with heartbeat status == "succeeded"
    if ctx.mass_scan_completed:
        return True, "MASS scan completed (heartbeat confirmed)", None

    # Fallback: findings with source.tool_type == "mass" exist
    mass_findings = ctx.findings_by_source.get("mass", [])
    if mass_findings:
        return True, "MASS scan results on file (from findings)", None

    return False, "No MASS scan completed", None


def _eval_scan_target_registered(rule, ctx):
    active_targets = [st for st in ctx.scan_targets if st.status == "active"]
    passed = len(active_targets) > 0
    return passed, f"{len(active_targets)} active scan target(s) registered" if passed else "No scan targets registered", {"count": len(active_targets)}


def _eval_no_prompt_injection(rule, ctx):
    pi_findings = [f for f in ctx.open_findings if "prompt_injection" in (f.category or "") or "prompt_injection" in (f.title or "").lower()]
    passed = len(pi_findings) == 0
    return passed, "0 prompt injection findings" if passed else f"{len(pi_findings)} prompt injection finding(s)", {"count": len(pi_findings)}


def _eval_guardrails_verified(rule, ctx):
    guardrail_findings = [f for f in ctx.open_findings if "guardrail" in (f.category or "") or "guardrail" in (f.title or "").lower()]
    passed = len(guardrail_findings) == 0
    return passed, "Guardrails verified (0 findings)" if passed else f"{len(guardrail_findings)} guardrail finding(s)", None


def _eval_no_pii_leakage(rule, ctx):
    pii_findings = [f for f in ctx.open_findings if "pii" in (f.title or "").lower() or "data_leakage" in (f.category or "")]
    passed = len(pii_findings) == 0
    return passed, "0 PII leakage findings" if passed else f"{len(pii_findings)} PII leakage finding(s)", None


def _eval_owasp_llm_top10_clear(rule, ctx):
    owasp_findings = [f for f in ctx.open_findings if (f.compliance_refs or {}).get("owasp_llm_top10")]
    passed = len(owasp_findings) == 0
    return passed, "OWASP LLM Top 10 clear" if passed else f"{len(owasp_findings)} OWASP LLM Top 10 finding(s)", None


def _eval_mass_risk_acceptable(rule, ctx):
    threshold = rule.threshold or 7.0
    high_risk = [f for f in ctx.open_findings if (f.cvss_score or 0) >= threshold and (f.source or {}).get("tool_type") == "mass"]
    passed = len(high_risk) == 0
    return passed, f"MASS risk below threshold ({threshold})" if passed else f"{len(high_risk)} finding(s) above risk threshold", None


def _eval_comprehensive_mass_scan(rule, ctx):
    # Check that MASS findings exist and have verdict data
    mass_with_verdict = [f for f in ctx.open_findings if f.verdict and (f.source or {}).get("tool_type") == "mass"]
    passed = len(mass_with_verdict) > 0 or _eval_mass_scan_completed(rule, ctx)[0]
    return passed, "Comprehensive MASS scan with verdicts" if passed else "No comprehensive MASS scan", None


def _eval_rai_eval_completed(rule, ctx):
    rai_findings = [f for f in ctx.open_findings if f.rai_eval_type]
    passed = len(rai_findings) > 0 or any(e.evidence_type in ("bias_benchmark", "red_team_report", "fairness_audit") for e in ctx.evidence_packages)
    return passed, "RAI evaluation completed" if passed else "No RAI evaluation on record", None


def _eval_model_card_documented(rule, ctx):
    model_card_evidence = [e for e in ctx.evidence_packages if e.evidence_type == "model_card"]
    passed = len(model_card_evidence) > 0
    return passed, "Model card documented" if passed else "No model card evidence", None


# FEU-sourced fairness rules

def _eval_fairness_case_defined(rule, ctx):
    return ctx.has_fairness_case, "Fairness case defined" if ctx.has_fairness_case else "No fairness case defined", None


def _eval_fairness_requirements_met(rule, ctx):
    if not ctx.has_frs:
        # No FRS, but check if evidence packages exist anyway (covers case where
        # agent submitted evidence without explicitly creating an FRS)
        if ctx.evidence_packages:
            return True, f"Fairness evidence submitted ({len(ctx.evidence_packages)} package(s))", None
        return False, "No fairness requirements spec", None
    if not ctx.evidence_packages:
        return False, "Fairness requirements defined but no evidence submitted", None
    return True, f"Fairness requirements met with {len(ctx.evidence_packages)} evidence package(s)", None


def _eval_fairness_evidence_current(rule, ctx):
    if not ctx.evidence_packages:
        return False, "No fairness evidence packages", None
    # Check freshness
    now = datetime.now(timezone.utc)
    fresh = [e for e in ctx.evidence_packages if e.expires_at is None or e.expires_at > now]
    passed = len(fresh) > 0
    return passed, f"{len(fresh)} current evidence package(s)" if passed else "All evidence packages expired", None


def _eval_fairness_attestation_signed(rule, ctx):
    return ctx.has_signed_attestation, "Fairness attestation signed" if ctx.has_signed_attestation else "No signed attestation", None


def _eval_fairness_hard_blocks_clear(rule, ctx):
    # No hard blocks = no failed critical fairness findings
    hard_blocks = [f for f in ctx.open_findings if f.category == "responsible_ai" and f.severity == "critical"]
    passed = len(hard_blocks) == 0
    return passed, "No fairness hard blocks" if passed else f"{len(hard_blocks)} fairness hard block(s)", None


def _eval_fairness_drift_acceptable(rule, ctx):
    threshold = rule.threshold or 0.1
    drifted = [s for s in ctx.monitoring_signals if s.signal_type == "fairness_drift" and s.value > threshold]
    passed = len(drifted) == 0
    return passed, "Fairness drift within limits" if passed else f"{len(drifted)} drift signal(s) above threshold", None


def _eval_fairness_context_receipt_valid(rule, ctx):
    return ctx.has_context_receipt, "Context receipt on file" if ctx.has_context_receipt else "No context receipt from agent", None


def _eval_fairness_exceptions_controlled(rule, ctx):
    uncontrolled = [e for e in ctx.fairness_exceptions if not e.compensating_controls]
    passed = len(uncontrolled) == 0
    return passed, "All fairness exceptions have compensating controls" if passed else f"{len(uncontrolled)} exception(s) without controls", None


def _eval_fairness_policy_deployed(rule, ctx):
    # Check that FRS + evidence + attestation all exist
    passed = ctx.has_frs and ctx.has_signed_attestation and len(ctx.evidence_packages) > 0
    return passed, "Fairness policy fully deployed" if passed else "Fairness policy not fully deployed", None


# Scanning integration rules

def _eval_compliance_score_threshold(rule, ctx):
    threshold = rule.threshold or 80.0
    if ctx.compliance_score is None:
        return False, "No compliance assessment available (run scan first)", None
    passed = ctx.compliance_score >= threshold
    return passed, f"Compliance score {ctx.compliance_score:.1f}% (threshold: {threshold}%)" if passed else f"Compliance score {ctx.compliance_score:.1f}% below threshold {threshold}%", {"score": ctx.compliance_score, "threshold": threshold}


def _eval_required_analyzers_completed(rule, ctx):
    # Check which analyzers are required based on project tier
    required = {"context", "mcp", "workflow", "attack_surface"}
    # Get additional requirements from rule parameters
    if hasattr(rule, "parameters") and rule.parameters:
        req_from_rule = rule.parameters.get("required_analyzers")
        if req_from_rule:
            required = set(req_from_rule)
    completed = set(ctx.completed_analyzers)
    missing = required - completed
    passed = len(missing) == 0
    msg = f"All required analyzers completed ({', '.join(sorted(completed))})" if passed else f"Missing analyzers: {', '.join(sorted(missing))}"
    return passed, msg, {"completed": list(completed), "missing": list(missing)}


def _eval_guardrail_coverage(rule, ctx):
    # Check that guardrail-related findings have been addressed
    # or that recommended guardrails have implementation evidence
    guardrail_issues = [
        f for f in ctx.open_findings
        if any(kw in (f.title or "").lower() for kw in ("guardrail", "input_validation", "output_filtering", "rate_limit"))
    ]
    passed = len(guardrail_issues) == 0
    return passed, "Guardrail coverage adequate (0 open guardrail findings)" if passed else f"{len(guardrail_issues)} open guardrail-related finding(s)", None


def _eval_security_review_clear(rule, ctx):
    # All /security-review findings must be closed or have exceptions
    open_reviews = [f for f in ctx.security_review_findings if f.status == "open"]
    passed = len(open_reviews) == 0
    total = len(ctx.security_review_findings)
    if total == 0:
        return False, "No security review findings on record (run /security-review)", None
    return passed, f"All {total} security review findings addressed" if passed else f"{len(open_reviews)} of {total} security review findings still open", {"open": len(open_reviews), "total": total}


def _eval_aiuc1_control_required(rule, ctx):
    """Check that a specific AIUC-1 sub-control is set to True in the org baseline.

    Rule parameters:
        category (str): AIUC-1 domain key (e.g. "security", "data_privacy")
        control  (str): Sub-control field key (e.g. "b001_1_adversarial_testing_report")
    """
    params = rule.parameters or {}
    category = params.get("category")
    control = params.get("control")

    if not category or not control:
        return False, "Rule misconfigured: missing 'category' or 'control' parameter", None

    control_ref = f"{category}.{control}"

    if not ctx.has_baseline:
        return False, f"No org baseline attached — cannot verify AIUC-1 control: {control_ref}", {
            "category": category, "control": control,
        }

    category_data = ctx.baseline_defaults.get(category, {})
    value = category_data.get(control)

    if value is True:
        return True, f"AIUC-1 control satisfied: {control_ref}", {
            "category": category, "control": control, "value": True,
        }
    if value is False:
        return False, f"AIUC-1 control not enabled: {control_ref} is set to False — enable it in the org baseline", {
            "category": category, "control": control, "value": False,
        }
    # None / missing
    return False, f"AIUC-1 control not assessed: {control_ref} has no value in the org baseline", {
        "category": category, "control": control, "value": None,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Unified framework_control_required evaluator
# ──────────────────────────────────────────────────────────────────────────────


def _check_findings_clear(ctx: _EvalContext, keywords: list[str], label: str):
    """Return pass if no open findings match any keyword in category or title."""
    matches = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower() for kw in keywords)
    ]
    passed = len(matches) == 0
    return passed, f"{label}: clear (0 findings)" if passed else f"{label}: {len(matches)} finding(s) open", {"count": len(matches)} if not passed else None


def _check_findings_by_tool(ctx: _EvalContext, tool_type: str, label: str):
    """Return pass if at least one finding from the given tool type exists (scan ran)."""
    hits = [f for f in ctx.open_findings if (f.source or {}).get("tool_type") == tool_type]
    all_hits = ctx.findings_by_source.get(tool_type, [])
    ran = len(all_hits) > 0
    return ran, f"{label}: scan completed ({len(all_hits)} finding(s) processed)" if ran else f"{label}: no {tool_type} scan results found", None


def _baseline_attestation(ctx: _EvalContext, framework: str, category: str, control: str, label: str):
    """Check framework-namespaced attestation in org baseline: baseline_defaults[framework][category][control]."""
    fw_data = ctx.baseline_defaults.get(framework, {})
    cat_data = fw_data.get(category, {}) if isinstance(fw_data, dict) else {}
    value = cat_data.get(control) if isinstance(cat_data, dict) else None
    ref = f"{framework}/{category}/{control}"
    if value is True:
        return True, f"{label}: attested in org baseline", {"ref": ref, "source": "attestation"}
    if value is False:
        return False, f"{label}: marked non-compliant in org baseline", {"ref": ref, "source": "attestation"}
    if not ctx.has_baseline:
        return False, f"{label}: no org baseline attached", {"ref": ref}
    return False, f"{label}: not yet attested — update org baseline or run automated scan", {"ref": ref, "source": "missing"}


# ── Per-framework dispatchers ──────────────────────────────────────────────────

def _eval_fw_aiuc1(category: str, control: str, ctx: _EvalContext):
    """AIUC-1: check baseline_defaults[category][control] (flat, backward-compat structure)."""
    control_ref = f"{category}.{control}"
    if not ctx.has_baseline:
        return False, f"No org baseline — cannot verify AIUC-1 {control_ref}", {}
    category_data = ctx.baseline_defaults.get(category, {})
    value = category_data.get(control)
    if value is True:
        return True, f"AIUC-1 control satisfied: {control_ref}", {"value": True}
    if value is False:
        return False, f"AIUC-1 control not enabled: {control_ref}", {"value": False}
    return False, f"AIUC-1 control not assessed: {control_ref}", {"value": None}


def _eval_fw_owasp_llm(category: str, control: str, ctx: _EvalContext):
    """OWASP LLM Top 10: scan-finding checks with attestation fallback."""
    _CHECKS = {
        "llm01_prompt_injection": lambda c: _check_findings_clear(c, ["prompt_injection"], "LLM01 Prompt Injection"),
        "llm02_insecure_output_handling": lambda c: _check_findings_clear(c, ["insecure_output", "output_handling"], "LLM02 Insecure Output Handling"),
        "llm03_training_data_poisoning": lambda c: _check_findings_clear(c, ["training_data_poisoning", "data_poisoning"], "LLM03 Training Data Poisoning"),
        "llm04_model_denial_of_service": lambda c: _check_findings_clear(c, ["model_dos", "denial_of_service", "resource_exhaustion"], "LLM04 Model DoS"),
        "llm05_supply_chain_vulnerabilities": lambda c: (
            any(e.evidence_type in ("sbom", "provenance") for e in c.evidence_packages),
            "LLM05 Supply Chain: provenance/SBOM evidence on file" if any(e.evidence_type in ("sbom", "provenance") for e in c.evidence_packages) else "LLM05 Supply Chain: no provenance or SBOM evidence",
            None,
        ),
        "llm06_sensitive_info_disclosure": lambda c: _check_findings_clear(c, ["pii", "data_leakage", "sensitive_info", "sensitive_information"], "LLM06 Sensitive Info Disclosure"),
        "llm07_insecure_plugin_design": lambda c: _check_findings_clear(c, ["insecure_plugin", "plugin_security", "tool_security"], "LLM07 Insecure Plugin Design"),
        "llm08_excessive_agency": lambda c: (
            c.has_env_profile,
            "LLM08 Excessive Agency: autonomy mode defined in environment profile" if c.has_env_profile else "LLM08 Excessive Agency: no environment profile — autonomy level not bounded",
            None,
        ),
        "llm09_overreliance": lambda c: (
            any(e.evidence_type == "model_card" for e in c.evidence_packages),
            "LLM09 Overreliance: model card documents limitations" if any(e.evidence_type == "model_card" for e in c.evidence_packages) else "LLM09 Overreliance: no model card documenting AI limitations",
            None,
        ),
        "llm10_model_theft": lambda c: _check_findings_clear(c, ["model_theft", "model_extraction", "model_inversion"], "LLM10 Model Theft"),
    }
    if category == "llm_top10" and control in _CHECKS:
        return _CHECKS[control](ctx)
    return False, f"Unknown OWASP LLM control: {category}/{control}", None


def _eval_fw_owasp_web(category: str, control: str, ctx: _EvalContext):
    """OWASP Web Top 10: finding-category checks + attestation fallback."""
    _CHECKS = {
        "a01_broken_access_control": lambda c: _check_findings_clear(c, ["access_control", "broken_access", "privilege_escalation", "idor"], "A01 Broken Access Control"),
        "a02_cryptographic_failures": lambda c: _check_findings_clear(c, ["crypto", "tls", "encryption", "certificate"], "A02 Cryptographic Failures"),
        "a03_injection": lambda c: _check_findings_clear(c, ["injection", "sql_injection", "xss", "command_injection", "ldap_injection"], "A03 Injection"),
        "a04_insecure_design": lambda c: (
            c.has_app_spec and c.has_compiled_package,
            "A04 Insecure Design: app spec and compiled context package present" if c.has_app_spec and c.has_compiled_package else "A04 Insecure Design: missing app spec or security context package",
            None,
        ),
        "a05_security_misconfiguration": lambda c: _check_findings_clear(c, ["misconfiguration", "security_misconfiguration", "default_credentials", "unnecessary_feature"], "A05 Security Misconfiguration"),
        "a06_vulnerable_components": lambda c: _check_findings_by_tool(c, "sca", "A06 Vulnerable Components SCA scan"),
        "a07_auth_failures": lambda c: _check_findings_clear(c, ["auth_failure", "authentication_failure", "broken_auth", "session_fixation"], "A07 Auth Failures"),
        "a08_software_integrity_failures": lambda c: (
            any(e.evidence_type in ("sbom", "provenance") for e in c.evidence_packages),
            "A08 Software Integrity: signing/provenance evidence on file" if any(e.evidence_type in ("sbom", "provenance") for e in c.evidence_packages) else "A08 Software Integrity: no signing or provenance evidence",
            None,
        ),
        "a09_logging_monitoring_failures": lambda c: (
            bool(c.scan_targets),
            "A09 Logging & Monitoring: scan targets registered (monitoring active)" if c.scan_targets else "A09 Logging & Monitoring: no scan targets — monitoring not confirmed",
            None,
        ),
        "a10_ssrf": lambda c: _check_findings_clear(c, ["ssrf", "server_side_request_forgery", "out_of_band"], "A10 SSRF"),
    }
    if category == "web_top10" and control in _CHECKS:
        return _CHECKS[control](ctx)
    return False, f"Unknown OWASP Web control: {category}/{control}", None


def _eval_fw_mitre_atlas(category: str, control: str, ctx: _EvalContext):
    """MITRE ATLAS: finding-category checks with attestation fallback for process controls."""
    _CHECKS = {
        ("reconnaissance", "aml_t0000_phishing_for_ml_info"): lambda c: _baseline_attestation(c, "mitre_atlas", category, control, "AML.T0000 Phishing for ML Info"),
        ("reconnaissance", "aml_t0001_discover_ml_artifacts"): lambda c: _check_findings_clear(c, ["ml_artifact_exposure", "model_exposure"], "AML.T0001 Discover ML Artifacts"),
        ("ml_attack_staging", "aml_t0016_obtain_capabilities"): lambda c: _baseline_attestation(c, "mitre_atlas", category, control, "AML.T0016 Obtain Capabilities"),
        ("ml_attack_staging", "aml_t0051_supply_chain_compromise"): lambda c: (
            any(e.evidence_type in ("sbom", "provenance") for e in c.evidence_packages),
            "AML.T0051 Supply Chain: SBOM/provenance evidence on file" if any(e.evidence_type in ("sbom", "provenance") for e in c.evidence_packages) else "AML.T0051 Supply Chain: no supply-chain integrity evidence",
            None,
        ),
        ("initial_access", "aml_t0012_valid_accounts"): lambda c: _check_findings_clear(c, ["credential_abuse", "account_compromise", "valid_account"], "AML.T0012 Valid Accounts"),
        ("ml_model_access", "aml_t0040_inference_api_access"): lambda c: (
            bool(c.scan_targets),
            "AML.T0040 Inference API: scan target registered — API monitored" if c.scan_targets else "AML.T0040 Inference API: no scan target registered for API",
            None,
        ),
        ("ml_model_access", "aml_t0043_craft_adversarial_data"): lambda c: (
            any(e.evidence_type in ("bias_benchmark", "red_team_report") for e in c.evidence_packages),
            "AML.T0043 Adversarial Data: adversarial/red-team testing evidence on file" if any(e.evidence_type in ("bias_benchmark", "red_team_report") for e in c.evidence_packages) else "AML.T0043 Adversarial Data: no adversarial testing evidence",
            None,
        ),
        ("exfiltration", "aml_t0057_llm_prompt_injection"): lambda c: _check_findings_clear(c, ["prompt_injection"], "AML.T0057 LLM Prompt Injection"),
        ("exfiltration", "aml_t0024_exfiltration_via_ml_inference"): lambda c: _check_findings_clear(c, ["data_exfiltration", "model_inversion", "membership_inference"], "AML.T0024 Exfiltration via ML Inference"),
        ("impact", "aml_t0029_denial_of_ml_service"): lambda c: _check_findings_clear(c, ["model_dos", "denial_of_service", "resource_exhaustion"], "AML.T0029 Denial of ML Service"),
        ("impact", "aml_t0031_erode_model_integrity"): lambda c: _baseline_attestation(c, "mitre_atlas", category, control, "AML.T0031 Erode Model Integrity"),
    }
    fn = _CHECKS.get((category, control))
    if fn:
        return fn(ctx)
    return False, f"Unknown MITRE ATLAS control: {category}/{control}", None


def _eval_fw_slsa(category: str, control: str, ctx: _EvalContext):
    """SLSA: evidence artifact checks."""
    has_provenance = any(e.evidence_type == "provenance" for e in ctx.evidence_packages)
    has_sbom = any(e.evidence_type == "sbom" for e in ctx.evidence_packages)
    has_signed = ctx.has_report.get("artifact_signed", False) or any(e.evidence_type == "artifact_signed" for e in ctx.evidence_packages)
    has_sca = len(ctx.findings_by_source.get("sca", [])) > 0 or any(st.tool_type == "sca" for st in ctx.scan_targets)
    critical_sca = [f for f in ctx.findings_by_source.get("sca", []) if f.severity == "critical"]
    has_license = ctx.has_report.get("license_compliance", False)

    _CHECKS = {
        ("provenance", "level_1"): (has_provenance, "SLSA L1: provenance artifact present" if has_provenance else "SLSA L1: no provenance artifact — attach via evidence package", None),
        ("provenance", "level_2"): (has_provenance, "SLSA L2: hosted build provenance present" if has_provenance else "SLSA L2: no hosted-build provenance evidence", None),
        ("provenance", "level_3"): (has_provenance, "SLSA L3: hardened build provenance present" if has_provenance else "SLSA L3: no hardened-build provenance evidence", None),
        ("artifacts", "sbom_generated"): (has_sbom, "SLSA SBOM: Software Bill of Materials on file" if has_sbom else "SLSA SBOM: no SBOM evidence package attached", None),
        ("artifacts", "artifact_signed"): (has_signed, "SLSA Signing: signed artifact evidence on file" if has_signed else "SLSA Signing: no signed artifact evidence", None),
        ("dependencies", "dependency_review"): (has_sca, "SLSA Dependency Review: SCA scan completed" if has_sca else "SLSA Dependency Review: no SCA scan results found", None),
        ("dependencies", "no_critical_cves"): (len(critical_sca) == 0, "SLSA CVEs: no critical CVEs in dependencies" if not critical_sca else f"SLSA CVEs: {len(critical_sca)} critical CVE(s) in dependencies", {"count": len(critical_sca)} if critical_sca else None),
        ("dependencies", "license_cleared"): (has_license, "SLSA Licenses: license compliance report on file" if has_license else "SLSA Licenses: no license compliance report", None),
    }
    result = _CHECKS.get((category, control))
    if result:
        return result
    return False, f"Unknown SLSA control: {category}/{control}", None


def _eval_fw_nist_rmf(category: str, control: str, ctx: _EvalContext):
    """NIST AI RMF: process/governance checks."""
    _CHECKS = {
        ("govern", "policy_defined"): lambda c: (c.has_baseline, "RMF Govern: org baseline (policy) attached" if c.has_baseline else "RMF Govern: no org baseline — AI risk policy not documented", None),
        ("govern", "roles_defined"): lambda c: _eval_iam_roles_defined(None, c),
        ("govern", "oversight_mechanism"): lambda c: (c.has_approval.get("promotion_gate", False) or c.has_approval.get("deployment_gate", False), "RMF Govern: approval/oversight records on file" if c.has_approval.get("promotion_gate") or c.has_approval.get("deployment_gate") else "RMF Govern: no oversight approval records found", None),
        ("map", "risk_categorized"): lambda c: (c.has_baseline and bool(c.baseline_defaults), "RMF Map: risk categorized via org baseline" if c.has_baseline else "RMF Map: org baseline not attached — risk not categorized", None),
        ("map", "threat_assessment"): lambda c: (c.has_compiled_package or len(c.security_review_findings) > 0, "RMF Map: threat assessment evidence present" if c.has_compiled_package or c.security_review_findings else "RMF Map: no compiled context or security review findings", None),
        ("map", "context_established"): lambda c: (c.has_app_spec, "RMF Map: deployment context established via app spec" if c.has_app_spec else "RMF Map: no app spec — deployment context not documented", None),
        ("measure", "metrics_defined"): lambda c: (c.has_report.get("environment_posture", False) or c.has_report.get("rai_posture", False), "RMF Measure: metrics report on file" if c.has_report.get("environment_posture") or c.has_report.get("rai_posture") else "RMF Measure: no posture or metrics report found", None),
        ("measure", "monitoring_plan"): lambda c: (bool(c.scan_targets), f"RMF Measure: {len(c.scan_targets)} scan target(s) active (monitoring configured)" if c.scan_targets else "RMF Measure: no scan targets — monitoring plan not configured", None),
        ("measure", "bias_evaluated"): lambda c: (any(e.evidence_type in ("bias_benchmark", "fairness_audit") for e in c.evidence_packages), "RMF Measure: bias/fairness evaluation evidence on file" if any(e.evidence_type in ("bias_benchmark", "fairness_audit") for e in c.evidence_packages) else "RMF Measure: no bias evaluation evidence", None),
        ("manage", "incident_plan"): lambda c: (c.has_report.get("residual_risk", False), "RMF Manage: residual risk/incident plan report on file" if c.has_report.get("residual_risk") else "RMF Manage: no residual risk report — incident plan not documented", None),
        ("manage", "risk_treatment"): lambda c: (c.has_compiled_package, "RMF Manage: compiled context package present (risk treatment documented)" if c.has_compiled_package else "RMF Manage: no compiled context package — risk treatment not documented", None),
        ("manage", "rollback_plan"): lambda c: (c.has_approval.get("promotion_gate", False), "RMF Manage: rollback plan evidenced by promotion approval record" if c.has_approval.get("promotion_gate") else "RMF Manage: no promotion approval record — rollback plan not on file", None),
    }
    fn = _CHECKS.get((category, control))
    if fn:
        return fn(ctx)
    return False, f"Unknown NIST AI RMF control: {category}/{control}", None


def _eval_fw_ssdf(category: str, control: str, ctx: _EvalContext):
    """NIST SSDF: secure software development practice checks."""
    _CHECKS = {
        ("prepare", "po1_security_requirements"): lambda c: (c.has_app_spec, "SSDF PO.1: security requirements in app spec" if c.has_app_spec else "SSDF PO.1: no app spec — security requirements not documented", None),
        ("prepare", "po2_roles_responsibilities"): lambda c: _eval_iam_roles_defined(None, c),
        ("prepare", "po3_third_party_management"): lambda c: (len(c.findings_by_source.get("sca", [])) > 0 or any(st.tool_type == "sca" for st in c.scan_targets), "SSDF PO.3: SCA scan active — third-party components managed" if len(c.findings_by_source.get("sca", [])) > 0 or any(st.tool_type == "sca" for st in c.scan_targets) else "SSDF PO.3: no SCA scan — third-party management not confirmed", None),
        ("produce", "pw1_security_design"): lambda c: (c.has_app_spec, "SSDF PW.1: security design in app spec" if c.has_app_spec else "SSDF PW.1: no app spec — security design not documented", None),
        ("produce", "pw2_threat_modeling"): lambda c: (any(e.evidence_type in ("model_card", "red_team_report") for e in c.evidence_packages) or c.has_compiled_package, "SSDF PW.2: threat model evidence present" if any(e.evidence_type in ("model_card", "red_team_report") for e in c.evidence_packages) or c.has_compiled_package else "SSDF PW.2: no threat model evidence", None),
        ("produce", "pw4_reusable_components"): lambda c: (c.has_compiled_package, "SSDF PW.4: compiled package confirms reusable component use" if c.has_compiled_package else "SSDF PW.4: no compiled context package", None),
        ("produce", "pw5_secure_defaults"): lambda c: _check_findings_clear(c, ["misconfiguration", "default_credentials", "insecure_default"], "SSDF PW.5 Secure Defaults"),
        ("produce", "pw6_code_review"): lambda c: _eval_security_review_clear(None, c),
        ("produce", "pw7_security_testing"): lambda c: (bool(c.scan_targets) or len(c.pearl_scan_findings) > 0, "SSDF PW.7: security testing scan results present" if c.scan_targets or c.pearl_scan_findings else "SSDF PW.7: no security testing evidence", None),
        ("produce", "pw8_vulnerability_scanning"): lambda c: _eval_scan_target_registered(None, c),
        ("respond", "rv1_disclosure_process"): lambda c: (c.has_report.get("control_coverage", False) or c.has_approval.get("deployment_gate", False), "SSDF RV.1: disclosure process evidenced by report/approval" if c.has_report.get("control_coverage") or c.has_approval.get("deployment_gate") else "SSDF RV.1: no disclosure process evidence", None),
        ("respond", "rv2_root_cause_analysis"): lambda c: (c.has_compiled_package, "SSDF RV.2: compiled context package includes remediation analysis" if c.has_compiled_package else "SSDF RV.2: no compiled context — root cause analysis not documented", None),
        ("respond", "rv3_remediation"): lambda c: (c.has_compiled_package and len(c.findings_by_severity.get("critical", [])) == 0, "SSDF RV.3: no critical open findings — remediation current" if c.has_compiled_package and not c.findings_by_severity.get("critical") else "SSDF RV.3: critical findings open or no compiled context", None),
    }
    fn = _CHECKS.get((category, control))
    if fn:
        return fn(ctx)
    return False, f"Unknown NIST SSDF control: {category}/{control}", None


# ── Dispatcher registry ────────────────────────────────────────────────────────

_FRAMEWORK_HANDLERS = {
    "aiuc1": _eval_fw_aiuc1,
    "owasp_llm": _eval_fw_owasp_llm,
    "owasp_web": _eval_fw_owasp_web,
    "mitre_atlas": _eval_fw_mitre_atlas,
    "slsa": _eval_fw_slsa,
    "nist_rmf": _eval_fw_nist_rmf,
    "ssdf": _eval_fw_ssdf,
}


def _eval_framework_control_required(rule, ctx):
    """Evaluate a specific control from any supported compliance framework.

    Parameters:
        framework: Framework key (aiuc1, owasp_llm, owasp_web, mitre_atlas, slsa, nist_rmf, ssdf)
        category:  Framework-specific category/group key
        control:   Specific control identifier within the category
    """
    params = rule.parameters or {}
    framework = params.get("framework")
    category = params.get("category")
    control = params.get("control")

    if not framework or not category or not control:
        return False, "Rule misconfigured: missing 'framework', 'category', or 'control' parameter", None

    handler = _FRAMEWORK_HANDLERS.get(framework)
    if handler is None:
        return False, f"Unsupported framework: '{framework}'", {"supported": list(_FRAMEWORK_HANDLERS)}

    passed, message, details = handler(category, control, ctx)
    base_details = {"framework": framework, "category": category, "control": control, **(details or {})}
    return passed, message, base_details


# ──────────────────────────────────────────────
# Rule evaluator registry
# ──────────────────────────────────────────────

RULE_EVALUATORS = {
    GateRuleType.PROJECT_REGISTERED: _eval_project_registered,
    GateRuleType.ORG_BASELINE_ATTACHED: _eval_org_baseline_attached,
    GateRuleType.APP_SPEC_DEFINED: _eval_app_spec_defined,
    GateRuleType.NO_HARDCODED_SECRETS: _eval_no_hardcoded_secrets,
    GateRuleType.UNIT_TESTS_EXIST: _eval_unit_tests_exist,
    GateRuleType.UNIT_TEST_COVERAGE: _eval_unit_test_coverage,
    GateRuleType.INTEGRATION_TEST_COVERAGE: _eval_integration_test_coverage,
    GateRuleType.SECURITY_BASELINE_TESTS: _eval_security_baseline_tests,
    GateRuleType.CRITICAL_FINDINGS_ZERO: _eval_critical_findings_zero,
    GateRuleType.HIGH_FINDINGS_ZERO: _eval_high_findings_zero,
    GateRuleType.DATA_CLASSIFICATIONS_DOCUMENTED: _eval_data_classifications_documented,
    GateRuleType.IAM_ROLES_DEFINED: _eval_iam_roles_defined,
    GateRuleType.NETWORK_BOUNDARIES_DECLARED: _eval_network_boundaries_declared,
    GateRuleType.ALL_CONTROLS_VERIFIED: _eval_all_controls_verified,
    GateRuleType.SECURITY_REVIEW_APPROVAL: _eval_security_review_approval,
    GateRuleType.EXEC_SPONSOR_APPROVAL: _eval_exec_sponsor_approval,
    GateRuleType.RESIDUAL_RISK_REPORT: _eval_residual_risk_report,
    GateRuleType.READ_ONLY_AUTONOMY: _eval_read_only_autonomy,
    # Scan targets
    GateRuleType.SCAN_TARGET_REGISTERED: _eval_scan_target_registered,
    # MASS AI security
    GateRuleType.MASS_SCAN_COMPLETED: _eval_mass_scan_completed,
    GateRuleType.NO_PROMPT_INJECTION: _eval_no_prompt_injection,
    GateRuleType.GUARDRAILS_VERIFIED: _eval_guardrails_verified,
    GateRuleType.NO_PII_LEAKAGE: _eval_no_pii_leakage,
    GateRuleType.OWASP_LLM_TOP10_CLEAR: _eval_owasp_llm_top10_clear,
    GateRuleType.MASS_RISK_ACCEPTABLE: _eval_mass_risk_acceptable,
    GateRuleType.COMPREHENSIVE_MASS_SCAN: _eval_comprehensive_mass_scan,
    GateRuleType.RAI_EVAL_COMPLETED: _eval_rai_eval_completed,
    GateRuleType.MODEL_CARD_DOCUMENTED: _eval_model_card_documented,
    # FEU fairness
    GateRuleType.FAIRNESS_CASE_DEFINED: _eval_fairness_case_defined,
    GateRuleType.FAIRNESS_REQUIREMENTS_MET: _eval_fairness_requirements_met,
    GateRuleType.FAIRNESS_EVIDENCE_CURRENT: _eval_fairness_evidence_current,
    GateRuleType.FAIRNESS_ATTESTATION_SIGNED: _eval_fairness_attestation_signed,
    GateRuleType.FAIRNESS_HARD_BLOCKS_CLEAR: _eval_fairness_hard_blocks_clear,
    GateRuleType.FAIRNESS_DRIFT_ACCEPTABLE: _eval_fairness_drift_acceptable,
    GateRuleType.FAIRNESS_CONTEXT_RECEIPT_VALID: _eval_fairness_context_receipt_valid,
    GateRuleType.FAIRNESS_EXCEPTIONS_CONTROLLED: _eval_fairness_exceptions_controlled,
    GateRuleType.FAIRNESS_POLICY_DEPLOYED: _eval_fairness_policy_deployed,
    # Scanning integration
    GateRuleType.COMPLIANCE_SCORE_THRESHOLD: _eval_compliance_score_threshold,
    GateRuleType.REQUIRED_ANALYZERS_COMPLETED: _eval_required_analyzers_completed,
    GateRuleType.GUARDRAIL_COVERAGE: _eval_guardrail_coverage,
    GateRuleType.SECURITY_REVIEW_CLEAR: _eval_security_review_clear,
    # AIUC-1 baseline control compliance (legacy — prefer FRAMEWORK_CONTROL_REQUIRED)
    GateRuleType.AIUC1_CONTROL_REQUIRED: _eval_aiuc1_control_required,
    # Unified multi-framework control evaluation
    GateRuleType.FRAMEWORK_CONTROL_REQUIRED: _eval_framework_control_required,
}
