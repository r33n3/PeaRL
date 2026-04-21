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
    AuditEventRepository,
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
from pearl.services.promotion.requirement_resolver import ResolvedRequirement, resolve_requirements


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
    source_environment: str | None = None,
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

    # Determine current environment — project.current_environment is authoritative.
    # env_profile.environment is a git-branch mapping and can lag behind resets/rollbacks.
    if source_environment:
        current_env = source_environment
    else:
        current_env = project.current_environment
        if not current_env:
            env_repo = EnvironmentProfileRepository(session)
            env_profile = await env_repo.get_by_project(project_id)
            current_env = env_profile.environment if env_profile else "pilot"

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
    ctx = await _build_eval_context(project_id, project, session, current_env, target_environment)

    # Evaluate each rule (static gate rules + dynamically derived BU requirements)
    rule_results = []
    static_rules = _parse_rules(gate.rules)

    # Inject FRAMEWORK_CONTROL_REQUIRED rules from BU requirements not already in gate
    existing_control_ids = {
        (r.parameters or {}).get("control")
        for r in static_rules
        if r.rule_type == GateRuleType.FRAMEWORK_CONTROL_REQUIRED
    }
    dynamic_rules = []
    for req in ctx.bu_requirements:
        if req.control_id not in existing_control_ids:
            # Map control_id to category: most BU controls are flat-keyed without category hierarchy
            # Use a generated rule_id and appropriate parameters
            dyn_rule = GateRuleDefinition(
                rule_id=generate_id("rule_"),
                rule_type=GateRuleType.FRAMEWORK_CONTROL_REQUIRED,
                description=f"{req.framework.upper()} control: {req.control_id}",
                ai_only=False,
                parameters={
                    "framework": req.framework,
                    "category": _infer_category(req.framework, req.control_id),
                    "control": req.control_id,
                    "requirement_level": req.requirement_level,
                },
            )
            dynamic_rules.append(dyn_rule)
            existing_control_ids.add(req.control_id)

    for rule_def in static_rules + dynamic_rules:
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

    await AuditEventRepository(session).append(
        event_id=generate_id("evt_"),
        resource_id=gate.gate_id,
        action_type="gate.evaluated",
        actor=None,
        details={
            "project_id": project_id,
            "evaluation_id": evaluation.evaluation_id,
            "source_environment": current_env,
            "target_environment": target_environment,
            "result": status.value,
            "auto_pass_eligible": gate.auto_pass,
        },
    )

    # Auto-pass eligibility check: gate has accumulated enough trust to skip human queue
    if gate.auto_pass and status == GateEvaluationStatus.PASSED:
        drift_stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.category == "drift_trend",
            FindingRow.status == "open",
        )
        drift_result = await session.execute(drift_stmt)
        open_drift = list(drift_result.scalars().all())
        if not open_drift:
            evaluation.auto_pass = True

    # Auto-create TaskPackets for FAIL results (idempotent — skip if one already exists)
    failed_results = [r for r in rule_results if r.result == GateRuleResult.FAIL]
    if failed_results:
        from pearl.repositories.task_packet_repo import TaskPacketRepository
        tp_repo = TaskPacketRepository(session)
        for fail_result in failed_results:
            try:
                existing = await tp_repo.get_open_for_rule(project_id, fail_result.rule_id)
                if not existing:
                    await tp_repo.create(
                        task_packet_id=generate_id("tp_"),
                        project_id=project_id,
                        environment=current_env,
                        trace_id=trace_id or generate_id("trace_"),
                        packet_data={
                            "task_type": "remediate_gate_blocker",
                            "status": "pending",
                            "rule_id": fail_result.rule_id,
                            "rule_type": fail_result.rule_type,
                            "finding_ids": (fail_result.details or {}).get("finding_ids", []),
                            "fix_guidance": _fix_guidance_for_rule(fail_result.rule_type),
                            "transition": f"{current_env}->{target_environment}",
                            "created_by": "gate_evaluator",
                            "blocker_message": fail_result.message,
                        },
                    )
            except Exception:
                pass  # TaskPacket creation is best-effort

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
        self.rejected_exceptions = []
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
        # BU-derived framework requirements for this transition
        self.bu_requirements: list[ResolvedRequirement] = []
        # Governance compliance
        self.has_claude_md_governance: bool = False
        # Cedar deployment status
        self.cedar_policy_active: bool = False
        # SonarQube quality gate status (from stored summary finding)
        self.sonarqube_qg_status: str | None = None
        # Snyk SCA context
        self.snyk_scan_seen: bool = False
        self.snyk_open_critical: int = 0
        self.snyk_open_high: int = 0
        # MASS 2.0 context
        self.mass_scan_seen: bool = False
        self.mass_risk_score: float = 0.0
        self.mass_verdict_risk_level: str | None = None  # "low"|"medium"|"high"|"critical"
        # LiteLLM compliance context
        self.litellm_scan_seen: bool = False
        # Factory run summary context
        self.has_factory_run_summary: bool = False
        self.factory_run_anomaly_count: int = 0


async def _build_eval_context(
    project_id: str,
    project,
    session: AsyncSession,
    source_env: str | None = None,
    target_env: str | None = None,
) -> _EvalContext:
    ctx = _EvalContext()
    ctx.project = project
    ctx.ai_enabled = project.ai_enabled

    # Check baseline — 3-tier resolution: project → BU → org-wide
    baseline_repo = OrgBaselineRepository(session)
    bu_id = getattr(project, "bu_id", None)
    baseline = await baseline_repo.get_for_project(project_id, bu_id=bu_id)
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
    ctx.rejected_exceptions = await exc_repo.get_rejected_by_project(project_id)

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

    # Scanning integration: pearl_scan findings (open only — for compliance scoring)
    ctx.pearl_scan_findings = [
        f for f in all_findings
        if (f.source or {}).get("tool_name", "").startswith("pearl_scan")
    ]

    # Load ALL findings for this project (all statuses) — needed for analyzer tracking
    # and security review gate (which checks resolved findings, not just open ones).
    all_scan_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
    )
    all_scan_result = await session.execute(all_scan_stmt)
    all_project_findings = list(all_scan_result.scalars().all())
    all_pearl_scan = [
        f for f in all_project_findings
        if (f.source or {}).get("tool_name", "").startswith("pearl_scan")
    ]

    # Security review findings — must use all statuses so resolved reviews count
    ctx.security_review_findings = [
        f for f in all_project_findings
        if (f.source or {}).get("tool_name") == "claude_security_review"
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

    # Load BU-derived framework requirements for the transition
    if source_env and target_env:
        try:
            ctx.bu_requirements = await resolve_requirements(
                project_id=project_id,
                source_env=source_env,
                target_env=target_env,
                session=session,
            )
        except Exception:
            ctx.bu_requirements = []

    # Snyk SCA context — derived from all_project_findings (already loaded above)
    snyk_findings = [f for f in all_project_findings if (f.source or {}).get("tool_name") == "snyk_sca"]
    ctx.snyk_scan_seen = len(snyk_findings) > 0
    open_snyk = [f for f in snyk_findings if f.status == "open"]
    ctx.snyk_open_critical = sum(1 for f in open_snyk if f.severity == "critical")
    ctx.snyk_open_high = sum(1 for f in open_snyk if f.severity == "high")

    # MASS 2.0 marker — identified by source.external_id == f"mass-marker-{project_id}"
    mass_marker = next(
        (f for f in all_project_findings if (f.source or {}).get("external_id") == f"mass-marker-{project_id}"),
        None,
    )
    ctx.mass_scan_seen = mass_marker is not None
    if mass_marker:
        ctx.mass_risk_score = float((mass_marker.full_data or {}).get("risk_score", 0.0))
        verdict = (mass_marker.full_data or {}).get("verdict", {})
        ctx.mass_verdict_risk_level = verdict.get("risk_level") if isinstance(verdict, dict) else None

    # Check CLAUDE.md governance block confirmation
    ctx.has_claude_md_governance = bool(getattr(project, "claude_md_verified", False))

    # SonarQube quality gate status — read from stored summary finding
    sonar_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["tool_name"].as_string() == "sonarqube_quality_gate",
    ).limit(1)
    sonar_result = await session.execute(sonar_stmt)
    sonar_summary = sonar_result.scalar_one_or_none()
    if sonar_summary:
        ctx.sonarqube_qg_status = (sonar_summary.full_data or {}).get("quality_gate_status")

    # Cedar deployment status
    try:
        from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository
        cedar_repo = CedarDeploymentRepository(session)
        org_id = getattr(project, "org_id", None) or "org_default"
        latest_cedar = await cedar_repo.get_latest_for_org(org_id)
        ctx.cedar_policy_active = (
            latest_cedar is not None
            and latest_cedar.status == "active"
            and latest_cedar.agentcore_deployment_id is not None
            and not latest_cedar.agentcore_deployment_id.startswith("dryrun_")
        )
    except Exception:
        ctx.cedar_policy_active = False

    # Snyk SCA context — count open findings by severity
    snyk_any_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["system"].as_string() == "snyk",
    ).limit(1)
    snyk_any_result = await session.execute(snyk_any_stmt)
    ctx.snyk_scan_seen = snyk_any_result.scalar_one_or_none() is not None

    snyk_open_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id,
        FindingRow.source["system"].as_string() == "snyk",
        FindingRow.status == "open",
    )
    snyk_open_result = await session.execute(snyk_open_stmt)
    for snyk_f in snyk_open_result.scalars().all():
        if snyk_f.severity == "critical":
            ctx.snyk_open_critical += 1
        elif snyk_f.severity == "high":
            ctx.snyk_open_high += 1

    # LiteLLM compliance context
    ctx.litellm_scan_seen = any(
        (f.source or {}).get("tool_name") == "litellm" for f in all_project_findings
    )

    # Factory run summary context
    try:
        from pearl.db.models.factory_run_summary import FactoryRunSummaryRow
        frun_stmt = (
            select(FactoryRunSummaryRow)
            .where(FactoryRunSummaryRow.project_id == project_id)
            .order_by(FactoryRunSummaryRow.created_at.desc())
            .limit(1)
        )
        frun_result = await session.execute(frun_stmt)
        latest_frun = frun_result.scalar_one_or_none()
        ctx.has_factory_run_summary = latest_frun is not None
        if latest_frun:
            ctx.factory_run_anomaly_count = len(latest_frun.anomaly_flags or [])
    except Exception:
        pass

    return ctx


_FIX_GUIDANCE: dict[str, str] = {
    "critical_findings_zero": "Resolve all critical-severity open findings. Check /findings?severity=critical.",
    "high_findings_zero": "Resolve all high-severity open findings. Check /findings?severity=high.",
    "no_hardcoded_secrets": "Remove hardcoded secrets from source code. Move to environment variables or a secrets manager.",
    "org_baseline_attached": "Attach an org baseline to this project via POST /org-baseline.",
    "app_spec_defined": "Define an application spec for this project via POST /projects/{id}/app-spec.",
    "unit_tests_exist": "Add unit test evidence via a compiled context package or evidence submission.",
    "scan_target_registered": "Register an active scan target for this project via POST /scan-targets.",
    "ai_scan_completed": "Run a PeaRL AI security scan via the runScan MCP tool. If an external scanner (MASS, SonarQube) is configured it will also satisfy this gate.",
    "mass_scan_completed": "Run a PeaRL AI security scan via the runScan MCP tool. If an external scanner (MASS, SonarQube) is configured it will also satisfy this gate.",
    "no_prompt_injection": "Resolve prompt injection findings. Implement input validation and prompt hardening.",
    "guardrails_verified": "Implement and verify AI guardrails. Address open guardrail findings.",
    "no_pii_leakage": "Fix PII leakage findings. Implement PII detection and filtering.",
    "framework_control_required": (
        "Inspect the project for evidence of this control (code, config, tests, reports), "
        "then call submitEvidence with evidence_type='attestation', "
        "control_id matching the rule's framework/category/control path, "
        "and findings summarising what you found. "
        "Alternatively set baseline_defaults[framework][category][control]=true in the org baseline."
    ),
    "aiuc1_control_required": (
        "Inspect the project for evidence of this AIUC-1 control, "
        "then call submitEvidence with evidence_type='attestation' and "
        "control_id='aiuc1/<category>/<control>'. "
        "Alternatively set the control to true in the org baseline defaults."
    ),
    "snyk_open_high_critical": "Resolve all Snyk critical and high severity findings, then re-run `snyk test --json` and POST to /integrations/snyk/ingest.",
    "security_review_clear": "Run /security-review and address all findings.",
    "compliance_score_threshold": (
        "Compliance score must reach 100%. Resolve all scan findings to raise the score. "
        "For known accepted risks that cannot be remediated, request an approved exception via "
        "createException — an active exception allows elevation even if the threshold is not met."
    ),
    "required_analyzers_completed": "Run all required analyzers. Trigger a full scan via POST /scan-targets/{id}/trigger.",
    "project_registered": "Ensure the project is properly registered in PeaRL.",
    "claude_md_governance_present": "Write the PeaRL governance block to the project's CLAUDE.md, then call the confirmClaudeMd MCP tool to confirm.",
    "residual_risk_report": "Generate a residual risk report via POST /projects/{id}/reports.",
    "data_classifications_documented": "Add data classifications to the application spec.",
    "iam_roles_defined": "Define IAM roles and trust boundaries in the application spec.",
    "network_boundaries_declared": "Declare network boundaries in the application spec or architecture section.",
    "fairness_case_defined": "Create a fairness case via POST /projects/{id}/fairness-case.",
    "fairness_requirements_met": "Submit fairness evidence packages to meet requirements.",
    "model_card_documented": "Submit a model card evidence package.",
    "owasp_llm_top10_clear": "Resolve OWASP LLM Top 10 findings. Run a security scan focused on LLM risks.",
    "cedar_policy_deployed": (
        "Cedar deployment is triggered automatically after promotion approval. "
        "Ensure all other gates pass, then call requestPromotion and await approval."
    ),
    "sonarqube_quality_gate": (
        "Fix failing quality gate conditions in SonarQube (see the sonarqube_link in the finding). "
        "Once the quality gate shows OK (or WARN for dev→preprod), "
        "call POST .../integrations/sonarqube/pull to refresh the status in PeaRL."
    ),
    "snyk_open_high_critical": (
        "Run `snyk test --json > snyk_results.json` in the project root, "
        "then POST the results to /projects/{id}/integrations/snyk/ingest. "
        "Fix or accept all HIGH/CRITICAL vulnerabilities before re-ingesting."
    ),
    "factory_run_summary_present": (
        "Complete a WTK factory run: register a workload, execute the agent task, "
        "then deregister with DELETE /workloads/{svid}?frun_id=<session_id>. "
        "Resolve any behavioral drift anomaly flags before promoting."
    ),
    "owasp_llm06_excessive_agency": "Declare agent.allowed_tools and agent.capability_scope in the app spec. Resolve any open excessive_agency findings from MASS scans.",
    "owasp_llm07_system_prompt_leakage": "Classify system prompts as confidential. Resolve open system_prompt_leakage findings. Implement prompt confidentiality controls.",
    "owasp_llm08_vector_weaknesses": "Validate RAG pipeline integrity. Resolve open vector_weakness or rag_poisoning findings. Implement retrieval input/output validation.",
    "owasp_llm10_unbounded_consumption": "Add agent.rate_limits or agent.cost_ceiling to app spec. Configure LiteLLM token limits. Resolve open unbounded_consumption findings.",
    "owasp_llm05_improper_output_handling": "Implement output sanitization and validation. Resolve open output_handling or output_injection findings.",
    "nhi_identity_registered": "Register a workload identity (SPIFFE/SVID) for the agent. Add agent.workload_identity to app spec or register a workload via POST /workloads.",
    "nhi_secrets_in_vault": "Move all agent credentials to a vault or secrets manager. Add agent.secrets_backend to app spec. Resolve open nhi_secret_exposure findings.",
    "nhi_credential_rotation_policy": "Define a credential rotation schedule. Add agent.credential_rotation or agent.key_rotation_days to app spec.",
    "nhi_least_privilege_verified": "Reduce agent API key and IAM scope to minimum required. Add agent.iam_scope to app spec. Resolve open nhi_overprivileged findings.",
    "nhi_token_expiry_configured": "Configure short-lived tokens (recommend ≤3600s). Add agent.token_ttl_seconds to app spec. Resolve open long_lived_token findings.",
    "agent_capability_scope_documented": "Add agent.allowed_tools or agent.capability_scope to app spec listing every tool/API the agent may call.",
    "agent_kill_switch_implemented": "Implement a halt mechanism for the agent. Add agent.kill_switch or agent.halt_endpoint to app spec.",
    "agent_blast_radius_assessed": "Document the maximum impact of a runaway agent. Add agent.blast_radius to app spec describing bounded worst-case impact.",
    "agent_communication_secured": "Secure inter-agent channels with mTLS. Add agent.communication_security to app spec. Resolve open mtls_missing findings.",
    "sbom_generated": "Generate an SBOM using Syft, Trivy, or CycloneDX. Submit via POST /projects/{id}/fairness-evidence with evidence_type='sbom'.",
}


def _fix_guidance_for_rule(rule_type: str) -> str:
    return _FIX_GUIDANCE.get(rule_type, f"Review and fix the failing gate rule: {rule_type}.")


def _infer_category(framework: str, control_id: str) -> str:
    """Infer the category for a framework control based on known structures."""
    _AIUC1_CATEGORY_MAP = {
        "a": "data_privacy", "b": "security", "c": "safety",
        "d": "reliability", "e": "accountability", "f": "society",
    }
    if framework == "aiuc1" and control_id and control_id[0] in _AIUC1_CATEGORY_MAP:
        return _AIUC1_CATEGORY_MAP[control_id[0]]
    _OWASP_LLM_CONTROLS = {
        "llm01_", "llm02_", "llm03_", "llm04_", "llm05_",
        "llm06_", "llm07_", "llm08_", "llm09_", "llm10_",
    }
    if framework == "owasp_llm" and any(control_id.startswith(p) for p in _OWASP_LLM_CONTROLS):
        return "llm_top10"
    if framework == "owasp_web" and control_id.startswith("a0"):
        return "web_top10"
    if framework == "mitre_atlas":
        if control_id.startswith("aml_t000"):
            return "reconnaissance"
        if control_id.startswith("aml_t001") or control_id.startswith("aml_t005"):
            return "ml_attack_staging"
        if control_id.startswith("aml_t0012"):
            return "initial_access"
        if control_id.startswith("aml_t004"):
            return "ml_model_access"
        if control_id.startswith("aml_t002") and "exfil" in control_id:
            return "exfiltration"
        if "aml_t0057" in control_id:
            return "exfiltration"
        return "impact"
    if framework == "slsa":
        if control_id in ("level_1", "level_2", "level_3"):
            return "provenance"
        if control_id in ("sbom_generated", "artifact_signed"):
            return "artifacts"
        return "dependencies"
    if framework == "nist_rmf":
        for cat in ("govern", "map", "measure", "manage"):
            pass  # fall through to flat key lookup
        return "govern"
    if framework == "ssdf":
        if control_id.startswith("po"):
            return "prepare"
        if control_id.startswith("pw"):
            return "produce"
        return "respond"
    return "general"


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
            # Check if a prior exception for this rule was rejected
            rejected = next(
                (
                    e for e in ctx.rejected_exceptions
                    if rule.rule_type in ((getattr(e, "scope", None) or {}).get("controls") or [])
                ),
                None,
            )
            if rejected:
                return RuleEvaluationResult(
                    rule_id=rule.rule_id,
                    rule_type=rule.rule_type,
                    result=GateRuleResult.FAIL,
                    message=(
                        f"EXCEPTION REJECTED ({rejected.exception_id}): {message}. "
                        f"The exception request for this rule was rejected by a reviewer. "
                        f"This issue must be fixed in the code — do not request another exception."
                    ),
                    details=details,
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


def _eval_claude_md_governance_present(rule, ctx):
    if ctx.has_claude_md_governance:
        return True, "PeaRL governance block confirmed in CLAUDE.md", None
    return (
        False,
        "PeaRL governance block not confirmed in CLAUDE.md — run POST /projects/{id}/confirm-claude-md after writing the block",
        {"fix": "Write the PeaRL governance block to CLAUDE.md, then call POST /projects/{id}/confirm-claude-md"},
    )


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
    findings = ctx.findings_by_severity.get("critical", [])
    count = len(findings)
    finding_ids = [f.finding_id for f in findings]
    return (
        count == 0,
        "0 critical findings" if count == 0 else f"{count} critical finding(s) open",
        {"count": count, "finding_ids": finding_ids},
    )


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


# AI security scan rules — satisfied by PeaRL built-in scan or any configured adapter

# AI scan tool types — any of these count as a completed AI security scan
_AI_SCAN_TOOL_TYPES = {"pearl_ai", "mass", "ai_scan"}


def _eval_snyk_open_high_critical(rule, ctx):
    if not ctx.snyk_scan_seen:
        return False, "No Snyk SCA scan ingested — run `snyk test --json` and POST to /integrations/snyk/ingest", None
    total = ctx.snyk_open_critical + ctx.snyk_open_high
    if total > 0:
        return (
            False,
            f"{total} open Snyk critical/high finding(s) ({ctx.snyk_open_critical} critical, {ctx.snyk_open_high} high)",
            {"critical": ctx.snyk_open_critical, "high": ctx.snyk_open_high},
        )
    return True, "No open Snyk critical or high severity findings", None


def _eval_ai_scan_completed(rule, ctx):
    # Check MASS 2.0 ingest marker (ingested via /integrations/mass/ingest)
    if ctx.mass_scan_seen:
        return True, "MASS 2.0 AI security scan completed", None

    # Primary check: scan target with succeeded status (any AI scan tool type)
    if ctx.mass_scan_completed:
        return True, "PeaRL AI security scan completed", None

    # Fallback: findings tagged with an AI scan tool type exist
    for tool_type in _AI_SCAN_TOOL_TYPES:
        if ctx.findings_by_source.get(tool_type):
            return True, f"AI security scan results on file (from {tool_type})", None

    return False, "No AI security scan completed — run the runScan MCP tool or POST to /integrations/mass/ingest", None


# Backward-compat alias
_eval_mass_scan_completed = _eval_ai_scan_completed


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


_BLOCKING_RISK_LEVELS = {"critical", "high"}


def _eval_ai_risk_acceptable(rule, ctx):
    threshold = rule.threshold or 7.0
    # Check MASS 2.0 risk score if a scan was ingested
    if ctx.mass_scan_seen:
        # Verdict risk_level takes precedence over numeric score when present
        if ctx.mass_verdict_risk_level in _BLOCKING_RISK_LEVELS:
            return (
                False,
                f"MASS 2.0 verdict risk level '{ctx.mass_verdict_risk_level}' exceeds acceptable threshold",
                {"verdict_risk_level": ctx.mass_verdict_risk_level, "threshold": threshold},
            )
        if ctx.mass_risk_score <= threshold:
            return True, f"MASS 2.0 risk score {ctx.mass_risk_score:.1f} is within threshold {threshold}", {"risk_score": ctx.mass_risk_score, "threshold": threshold}
        return False, f"MASS 2.0 risk score {ctx.mass_risk_score:.1f} exceeds threshold {threshold}", {"risk_score": ctx.mass_risk_score, "threshold": threshold}
    if not ctx.mass_scan_seen and not ctx.mass_scan_completed:
        return False, "No MASS 2.0 scan ingested — POST to /integrations/mass/ingest", None
    # Fallback: check findings from any AI scan source
    high_risk = [
        f for f in ctx.open_findings
        if (f.cvss_score or 0) >= threshold
        and (f.source or {}).get("tool_type") in _AI_SCAN_TOOL_TYPES
    ]
    passed = len(high_risk) == 0
    return passed, f"AI scan risk below threshold ({threshold})" if passed else f"{len(high_risk)} finding(s) above risk threshold", None


# Backward-compat alias
_eval_mass_risk_acceptable = _eval_ai_risk_acceptable


def _eval_comprehensive_ai_scan(rule, ctx):
    # Comprehensive: AI scan findings with verdict data present, or scan completed
    ai_with_verdict = [
        f for f in ctx.open_findings
        if f.verdict and (f.source or {}).get("tool_type") in _AI_SCAN_TOOL_TYPES
    ]
    passed = len(ai_with_verdict) > 0 or _eval_ai_scan_completed(rule, ctx)[0]
    return passed, "Comprehensive AI security scan with verdicts" if passed else "No comprehensive AI security scan", None


# Backward-compat alias
_eval_comprehensive_mass_scan = _eval_comprehensive_ai_scan


def _eval_cedar_policy_deployed(rule, ctx):
    if ctx.cedar_policy_active:
        return True, "Cedar policy bundle active in AgentCore", None
    return (
        False,
        "No active Cedar policy bundle deployed to AgentCore — "
        "all other gates must pass first, then approval triggers deployment",
        None,
    )


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


def _eval_sonarqube_quality_gate(rule, ctx):
    """Pass if SonarQube quality gate is OK (or WARN for non-prod gates).

    For dev→preprod: OK or WARN is acceptable.
    For preprod→prod: only OK passes.
    Rule description distinguishes the threshold.
    """
    if ctx.sonarqube_qg_status is None:
        return (
            False,
            "No SonarQube quality gate data — run POST .../integrations/sonarqube/pull first",
            None,
        )
    # preprod→prod requires OK; other gates accept OK or WARN
    description = getattr(rule, "description", "")
    require_ok_only = "OK)" in description  # set by default_gates description
    status = ctx.sonarqube_qg_status
    if status == "OK":
        return True, f"SonarQube quality gate: OK", {"quality_gate": status}
    if status == "WARN" and not require_ok_only:
        return True, f"SonarQube quality gate: WARN (acceptable for this stage)", {"quality_gate": status}
    return (
        False,
        f"SonarQube quality gate: {status} — fix failing conditions in SonarQube, then re-pull",
        {"quality_gate": status},
    )


def _eval_snyk_open_high_critical(rule, ctx):
    if not ctx.snyk_scan_seen:
        return (
            False,
            "No Snyk SCA scan ingested — run snyk test and POST to /integrations/snyk/ingest",
            None,
        )
    total = ctx.snyk_open_critical + ctx.snyk_open_high
    if total > 0:
        return (
            False,
            f"Snyk SCA: {total} HIGH/CRITICAL open ({ctx.snyk_open_critical} critical, {ctx.snyk_open_high} high) — fix and re-run snyk test",
            {"critical": ctx.snyk_open_critical, "high": ctx.snyk_open_high},
        )
    return True, "Snyk SCA: no open HIGH/CRITICAL vulnerabilities", {"critical": 0, "high": 0}


def _eval_litellm_compliance(rule, ctx):
    if not ctx.litellm_scan_seen:
        return (
            False,
            "No LiteLLM compliance scan ingested — configure LiteLLM integration and pull findings first",
            None,
        )
    open_litellm = [
        f for f in ctx.open_findings
        if (f.source or {}).get("tool_name") == "litellm"
    ]
    if open_litellm:
        return (
            False,
            f"LiteLLM: {len(open_litellm)} compliance violation(s) open — fix policy violations in LiteLLM virtual key configuration",
            {"violations": len(open_litellm)},
        )
    return True, "LiteLLM: no open compliance violations", {"violations": 0}


def _eval_factory_run_summary_present(rule, ctx):
    if not ctx.has_factory_run_summary:
        return (
            False,
            "No factory run summary — complete a WTK run with DELETE /workloads/{svid}?frun_id=<session_id>",
            None,
        )
    if ctx.factory_run_anomaly_count > 0:
        return (
            False,
            f"Factory run has {ctx.factory_run_anomaly_count} open anomaly flag(s) — resolve behavioral drift findings",
            {"anomaly_count": ctx.factory_run_anomaly_count},
        )
    return True, "Factory run summary present with no anomaly flags", None


# ── OWASP LLM Top 10 discrete rules ──────────────────────────────────────────

def _eval_owasp_llm06_excessive_agency(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("excessive_agency", "excessive_autonomy", "unbounded_action", "capability_scope"))
    ]
    if findings:
        return False, f"LLM06 Excessive Agency: {len(findings)} open finding(s) — restrict agent tool/action scope", {"count": len(findings), "finding_ids": [f.finding_id for f in findings]}
    # Fallback: app spec must declare capability scope
    agent_spec = ctx.app_spec_data.get("agent", {}) or ctx.app_spec_data.get("ai_agent", {})
    allowed_tools = agent_spec.get("allowed_tools") or agent_spec.get("capabilities") or agent_spec.get("capability_scope")
    if not allowed_tools and ctx.has_app_spec:
        return False, "LLM06 Excessive Agency: app spec missing 'agent.allowed_tools' or 'agent.capability_scope' — declare what the agent is permitted to do", None
    if ctx.has_app_spec and allowed_tools:
        return True, "LLM06 Excessive Agency: agent capability scope declared in app spec, 0 open findings", None
    return False, "LLM06 Excessive Agency: no app spec and no scan findings to confirm scope — define agent.allowed_tools in app spec", None


def _eval_owasp_llm07_system_prompt_leakage(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("system_prompt_leakage", "system_prompt_exposure", "prompt_leakage", "system_prompt"))
    ]
    passed = len(findings) == 0
    if not passed:
        return False, f"LLM07 System Prompt Leakage: {len(findings)} open finding(s) — classify and protect system prompts", {"count": len(findings)}
    return True, "LLM07 System Prompt Leakage: no open findings", None


def _eval_owasp_llm08_vector_weaknesses(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("vector_weakness", "embedding_weakness", "rag_poisoning", "retrieval_poisoning", "vector_store"))
    ]
    passed = len(findings) == 0
    if not passed:
        return False, f"LLM08 Vector/Embedding Weaknesses: {len(findings)} open finding(s) — validate RAG pipeline integrity", {"count": len(findings)}
    # If no RAG in app spec, skip as not applicable
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    uses_rag = agent_spec.get("uses_rag") or agent_spec.get("rag_enabled") or "rag" in str(ctx.app_spec_data).lower()
    if not uses_rag:
        return True, "LLM08 Vector/Embedding Weaknesses: no RAG pipeline declared — not applicable", None
    return True, "LLM08 Vector/Embedding Weaknesses: 0 open findings", None


def _eval_owasp_llm10_unbounded_consumption(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("unbounded_consumption", "resource_exhaustion", "cost_anomaly", "token_limit", "rate_limit_missing"))
    ]
    if findings:
        return False, f"LLM10 Unbounded Consumption: {len(findings)} open finding(s) — implement token/cost limits", {"count": len(findings)}
    # Check app spec for rate limiting declaration
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    has_limits = agent_spec.get("max_tokens") or agent_spec.get("rate_limits") or agent_spec.get("cost_ceiling")
    if has_limits:
        return True, "LLM10 Unbounded Consumption: consumption limits declared in app spec, 0 open findings", None
    # LiteLLM compliance implicitly covers this if scan has been done
    if ctx.litellm_scan_seen:
        return True, "LLM10 Unbounded Consumption: LiteLLM compliance scan covers rate limiting — 0 open findings", None
    return False, "LLM10 Unbounded Consumption: no rate/token limits declared in app spec (add agent.rate_limits or agent.cost_ceiling) and no LiteLLM scan ingested", None


def _eval_owasp_llm05_improper_output_handling(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("output_handling", "improper_output", "output_injection", "output_sanitization", "xss"))
    ]
    passed = len(findings) == 0
    if not passed:
        return False, f"LLM05 Improper Output Handling: {len(findings)} open finding(s) — implement output validation and sanitization", {"count": len(findings)}
    return True, "LLM05 Improper Output Handling: 0 open findings", None


# ── NHI (Non-Human Identity) rules ───────────────────────────────────────────

def _eval_nhi_identity_registered(rule, ctx):
    # Check app spec for workload identity declaration
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    identity = agent_spec.get("workload_identity") or agent_spec.get("spiffe_id") or agent_spec.get("svid")
    if identity:
        return True, f"NHI Identity: workload identity declared in app spec ({identity})", None
    # Check scan targets — a registered workload with an svid counts
    svid_targets = [st for st in ctx.scan_targets if getattr(st, "svid", None)]
    if svid_targets:
        return True, f"NHI Identity: {len(svid_targets)} workload(s) with SPIFFE identity registered", None
    # Check open findings for NHI identity gaps
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("nhi_identity", "workload_identity", "identity_missing", "no_workload_identity"))
    ]
    if findings:
        return False, f"NHI Identity: {len(findings)} open identity finding(s) — register a workload identity (SPIFFE/SVID)", {"count": len(findings)}
    return False, "NHI Identity: no workload identity declared — add agent.workload_identity to app spec or register a workload with an SVID", None


def _eval_nhi_secrets_in_vault(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("nhi_secret_exposure", "secret_in_env", "credential_in_config", "secret_not_in_vault", "env_var_secret"))
    ]
    if findings:
        return False, f"NHI Secrets: {len(findings)} open finding(s) — move agent credentials to a vault or secrets manager", {"count": len(findings)}
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    secrets_backend = agent_spec.get("secrets_backend") or agent_spec.get("vault_config")
    if secrets_backend:
        return True, f"NHI Secrets: secrets backend declared in app spec ({secrets_backend}), 0 open findings", None
    # If no vault declared and no open findings, pass with warning guidance embedded in message
    return True, "NHI Secrets: no open secret-exposure findings (ensure agent credentials are stored in a vault, not env vars)", None


def _eval_nhi_credential_rotation_policy(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("credential_rotation", "static_credential", "rotation_policy_missing"))
    ]
    if findings:
        return False, f"NHI Credential Rotation: {len(findings)} open finding(s) — define a credential rotation policy", {"count": len(findings)}
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    rotation = agent_spec.get("credential_rotation") or agent_spec.get("key_rotation_days")
    if rotation:
        return True, f"NHI Credential Rotation: rotation policy declared in app spec", None
    return False, "NHI Credential Rotation: no rotation policy declared — add agent.credential_rotation or agent.key_rotation_days to app spec", None


def _eval_nhi_least_privilege_verified(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("nhi_overprivileged", "excessive_privilege", "overpermissioned", "least_privilege"))
    ]
    if findings:
        return False, f"NHI Least Privilege: {len(findings)} open overprivilege finding(s) — reduce agent API key/IAM scope", {"count": len(findings)}
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    iam_scope = agent_spec.get("iam_scope") or agent_spec.get("api_key_permissions") or agent_spec.get("permission_scope")
    if iam_scope:
        return True, "NHI Least Privilege: permission scope declared in app spec, 0 open overprivilege findings", None
    return False, "NHI Least Privilege: no permission scope declared — add agent.iam_scope or agent.api_key_permissions to app spec", None


def _eval_nhi_token_expiry_configured(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("long_lived_token", "token_no_expiry", "static_token", "token_expiry_missing"))
    ]
    if findings:
        return False, f"NHI Token Expiry: {len(findings)} open finding(s) — configure short-lived tokens with max TTL", {"count": len(findings)}
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    token_ttl = agent_spec.get("token_ttl_seconds") or agent_spec.get("token_max_ttl") or agent_spec.get("token_expiry")
    if token_ttl:
        return True, f"NHI Token Expiry: token TTL configured in app spec ({token_ttl}s max)", None
    return False, "NHI Token Expiry: no token expiry configured — add agent.token_ttl_seconds to app spec (recommend ≤3600s)", None


# ── Agent operational governance ──────────────────────────────────────────────

def _eval_agent_capability_scope_documented(rule, ctx):
    agent_spec = ctx.app_spec_data.get("agent", {}) or ctx.app_spec_data.get("ai_agent", {})
    allowed = agent_spec.get("allowed_tools") or agent_spec.get("capabilities") or agent_spec.get("capability_scope")
    if allowed:
        return True, f"Agent Capability Scope: declared in app spec", None
    return False, "Agent Capability Scope: missing — add agent.allowed_tools or agent.capability_scope to app spec listing what tools/APIs the agent may call", None


def _eval_agent_kill_switch_implemented(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("kill_switch_missing", "agent_control_missing", "no_interrupt", "no_kill_switch"))
    ]
    if findings:
        return False, f"Agent Kill Switch: {len(findings)} open finding(s) — implement a mechanism to halt the agent mid-run", {"count": len(findings)}
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    kill_switch = agent_spec.get("kill_switch") or agent_spec.get("interrupt_mechanism") or agent_spec.get("halt_endpoint")
    if kill_switch:
        return True, "Agent Kill Switch: mechanism declared in app spec", None
    return False, "Agent Kill Switch: not declared — add agent.kill_switch (true/endpoint) to app spec confirming a halt mechanism exists", None


def _eval_agent_blast_radius_assessed(rule, ctx):
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    blast_radius = agent_spec.get("blast_radius") or agent_spec.get("max_impact") or agent_spec.get("blast_radius_assessment")
    if blast_radius:
        return True, "Agent Blast Radius: assessment present in app spec", None
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("blast_radius", "impact_unbound", "runaway_agent"))
    ]
    if findings:
        return False, f"Agent Blast Radius: {len(findings)} open finding(s) — bound and document maximum agent impact", {"count": len(findings)}
    return False, "Agent Blast Radius: not assessed — add agent.blast_radius to app spec describing maximum impact if the agent runs unconstrained", None


def _eval_agent_communication_secured(rule, ctx):
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("insecure_agent_channel", "agent_communication", "plaintext_agent", "mtls_missing", "agent_channel"))
    ]
    if findings:
        return False, f"Agent Communication: {len(findings)} open finding(s) — secure inter-agent channels with mTLS or equivalent", {"count": len(findings)}
    agent_spec = ctx.app_spec_data.get("agent", {}) or {}
    comm_security = agent_spec.get("communication_security") or agent_spec.get("mtls_enabled") or agent_spec.get("channel_security")
    if comm_security:
        return True, "Agent Communication: channel security declared in app spec, 0 open findings", None
    return True, "Agent Communication: no open channel-security findings (add agent.communication_security to app spec for explicit attestation)", None


# ── Supply chain integrity ────────────────────────────────────────────────────

def _eval_sbom_generated(rule, ctx):
    sbom_evidence = [e for e in ctx.evidence_packages if getattr(e, "evidence_type", None) in ("sbom", "provenance")]
    if sbom_evidence:
        return True, f"SBOM: {len(sbom_evidence)} SBOM/provenance evidence package(s) on file", None
    findings = [
        f for f in ctx.open_findings
        if any(kw in (f.category or "").lower() or kw in (f.title or "").lower()
               for kw in ("sbom_missing", "no_sbom", "provenance_missing"))
    ]
    if findings:
        return False, f"SBOM: {len(findings)} open finding(s) — generate an SBOM (Syft, Trivy, or CycloneDX)", {"count": len(findings)}
    return False, "SBOM: no SBOM evidence — generate an SBOM and submit via POST /projects/{id}/fairness-evidence with evidence_type='sbom'", None


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
    """Check framework control is satisfied via org baseline boolean OR submitted evidence package.

    Pass conditions (in priority order):
    1. baseline_defaults[framework][category][control] is True
    2. An evidence package of type 'attestation' with matching control_id exists
    Fail if explicitly set to False in baseline (non-compliant declaration).
    """
    ref = f"{framework}/{category}/{control}"

    # 1. Check org baseline boolean
    fw_data = ctx.baseline_defaults.get(framework, {})
    cat_data = fw_data.get(category, {}) if isinstance(fw_data, dict) else {}
    value = cat_data.get(control) if isinstance(cat_data, dict) else None
    if value is True:
        return True, f"{label}: attested in org baseline", {"ref": ref, "source": "baseline"}
    if value is False:
        return False, f"{label}: marked non-compliant in org baseline", {"ref": ref, "source": "baseline"}

    # 2. Check submitted evidence packages for a matching attestation
    matching_evidence = [
        e for e in ctx.evidence_packages
        if getattr(e, "evidence_type", None) == "attestation"
        and (getattr(e, "evidence_data", None) or {}).get("control_id") == ref
    ]
    if matching_evidence:
        latest = matching_evidence[-1]
        attested_by = (getattr(latest, "evidence_data", None) or {}).get("attested_by", "agent")
        return True, f"{label}: validated by {attested_by} — evidence on file", {"ref": ref, "source": "evidence_package"}

    if not ctx.has_baseline:
        return False, f"{label}: no org baseline — attest via submitEvidence(evidence_type='attestation', control_id='{ref}')", {"ref": ref}
    return False, f"{label}: not yet attested — inspect the project and call submitEvidence(evidence_type='attestation', control_id='{ref}')", {"ref": ref, "source": "missing"}


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
    # Snyk SCA
    GateRuleType.SNYK_OPEN_HIGH_CRITICAL: _eval_snyk_open_high_critical,
    # AI security scan (built-in + adapter)
    GateRuleType.AI_SCAN_COMPLETED: _eval_ai_scan_completed,
    GateRuleType.NO_PROMPT_INJECTION: _eval_no_prompt_injection,
    GateRuleType.GUARDRAILS_VERIFIED: _eval_guardrails_verified,
    GateRuleType.NO_PII_LEAKAGE: _eval_no_pii_leakage,
    GateRuleType.OWASP_LLM_TOP10_CLEAR: _eval_owasp_llm_top10_clear,
    GateRuleType.AI_RISK_ACCEPTABLE: _eval_ai_risk_acceptable,
    GateRuleType.COMPREHENSIVE_AI_SCAN: _eval_comprehensive_ai_scan,
    GateRuleType.CEDAR_POLICY_DEPLOYED: _eval_cedar_policy_deployed,
    # Legacy names — map to same evaluators for backward compat with stored gate rows
    GateRuleType.MASS_SCAN_COMPLETED: _eval_ai_scan_completed,
    GateRuleType.MASS_RISK_ACCEPTABLE: _eval_ai_risk_acceptable,
    GateRuleType.COMPREHENSIVE_MASS_SCAN: _eval_comprehensive_ai_scan,
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
    GateRuleType.SONARQUBE_QUALITY_GATE: _eval_sonarqube_quality_gate,
    GateRuleType.SNYK_OPEN_HIGH_CRITICAL: _eval_snyk_open_high_critical,
    # AIUC-1 baseline control compliance (legacy — prefer FRAMEWORK_CONTROL_REQUIRED)
    GateRuleType.AIUC1_CONTROL_REQUIRED: _eval_aiuc1_control_required,
    # Unified multi-framework control evaluation
    GateRuleType.FRAMEWORK_CONTROL_REQUIRED: _eval_framework_control_required,
    # Governance compliance
    GateRuleType.CLAUDE_MD_GOVERNANCE_PRESENT: _eval_claude_md_governance_present,
    # LiteLLM AI gateway compliance
    GateRuleType.LITELLM_COMPLIANCE: _eval_litellm_compliance,
    # Factory run summary gate
    GateRuleType.FACTORY_RUN_SUMMARY_PRESENT: _eval_factory_run_summary_present,
    # OWASP LLM Top 10 discrete rules
    GateRuleType.OWASP_LLM06_EXCESSIVE_AGENCY: _eval_owasp_llm06_excessive_agency,
    GateRuleType.OWASP_LLM07_SYSTEM_PROMPT_LEAKAGE: _eval_owasp_llm07_system_prompt_leakage,
    GateRuleType.OWASP_LLM08_VECTOR_WEAKNESSES: _eval_owasp_llm08_vector_weaknesses,
    GateRuleType.OWASP_LLM10_UNBOUNDED_CONSUMPTION: _eval_owasp_llm10_unbounded_consumption,
    GateRuleType.OWASP_LLM05_IMPROPER_OUTPUT_HANDLING: _eval_owasp_llm05_improper_output_handling,
    # NHI (Non-Human Identity) rules
    GateRuleType.NHI_IDENTITY_REGISTERED: _eval_nhi_identity_registered,
    GateRuleType.NHI_SECRETS_IN_VAULT: _eval_nhi_secrets_in_vault,
    GateRuleType.NHI_CREDENTIAL_ROTATION_POLICY: _eval_nhi_credential_rotation_policy,
    GateRuleType.NHI_LEAST_PRIVILEGE_VERIFIED: _eval_nhi_least_privilege_verified,
    GateRuleType.NHI_TOKEN_EXPIRY_CONFIGURED: _eval_nhi_token_expiry_configured,
    # Agent operational governance
    GateRuleType.AGENT_CAPABILITY_SCOPE_DOCUMENTED: _eval_agent_capability_scope_documented,
    GateRuleType.AGENT_KILL_SWITCH_IMPLEMENTED: _eval_agent_kill_switch_implemented,
    GateRuleType.AGENT_BLAST_RADIUS_ASSESSED: _eval_agent_blast_radius_assessed,
    GateRuleType.AGENT_COMMUNICATION_SECURED: _eval_agent_communication_secured,
    # Supply chain integrity
    GateRuleType.SBOM_GENERATED: _eval_sbom_generated,
}
