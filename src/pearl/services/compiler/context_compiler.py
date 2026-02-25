"""Context compilation engine - merges org-baseline + app-spec + environment-profile."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.errors.exceptions import ValidationError
from pearl.models.compiled_context import (
    ApprovalCheckpoint,
    AutonomousRemediationEligibility,
    AutonomyPolicy,
    ChangeReassessmentTriggers,
    CompiledContextPackage,
    CompiledFrom,
    DataHandlingRequirements,
    Fairness,
    IamRequirements,
    NetworkRequirements,
    Oversight,
    PackageMetadata,
    ProjectIdentity,
    RemediationRule,
    RequiredTests,
    ResponsibleAiRequirements,
    SecurityRequirements,
    ToolAndModelConstraints,
    Transparency,
)
from pearl.models.common import Reference, TraceabilityRef
from pearl.repositories.app_spec_repo import AppSpecRepository
from pearl.repositories.compiled_package_repo import CompiledPackageRepository
from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
from pearl.repositories.exception_repo import ExceptionRepository
from pearl.repositories.org_baseline_repo import OrgBaselineRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.compiler.integrity import compute_integrity
from pearl.services.id_generator import generate_id


async def compile_context(
    project_id: str,
    trace_id: str,
    apply_exceptions: bool = True,
    session: AsyncSession | None = None,
) -> CompiledContextPackage:
    """Compile layered context into a CompiledContextPackage.

    Precedence: environment_profile > app_spec > org_baseline
    """
    # Load all inputs
    project_repo = ProjectRepository(session)
    project = await project_repo.get(project_id)
    if not project:
        raise ValidationError(f"Project '{project_id}' not found")

    baseline_repo = OrgBaselineRepository(session)
    baseline = await baseline_repo.get_by_project(project_id)
    if not baseline:
        raise ValidationError(f"Org baseline not found for project '{project_id}'")

    app_spec_repo = AppSpecRepository(session)
    app_spec = await app_spec_repo.get_by_project(project_id)
    if not app_spec:
        raise ValidationError(f"Application spec not found for project '{project_id}'")

    env_profile_repo = EnvironmentProfileRepository(session)
    env_profile = await env_profile_repo.get_by_project(project_id)
    if not env_profile:
        raise ValidationError(f"Environment profile not found for project '{project_id}'")

    defaults = baseline.defaults
    spec = app_spec.full_spec

    # Build autonomy policy from environment profile
    autonomy_policy = AutonomyPolicy(
        mode=env_profile.autonomy_mode,
        allowed_actions=env_profile.allowed_capabilities or [],
        blocked_actions=env_profile.blocked_capabilities or [],
        approval_required_for=_build_approval_required_for(spec),
    )

    # Build security requirements
    security_requirements = SecurityRequirements(
        required_controls=_build_required_controls(defaults, spec),
        prohibited_patterns=_build_prohibited_patterns(defaults),
    )

    # Build RAI requirements
    rai_requirements = _build_rai_requirements(defaults, spec, project.ai_enabled)

    # Build IAM requirements
    iam_requirements = IamRequirements(
        least_privilege_required=defaults.get("iam", {}).get("least_privilege_required", False),
    )

    # Build network requirements
    network_requirements = _build_network_requirements(spec)

    # Build data handling
    data_handling = _build_data_handling(spec)

    # Build tool and model constraints
    tool_constraints = _build_tool_constraints(env_profile)

    # Build required tests
    required_tests = _build_required_tests(defaults, project.ai_enabled)

    # Build approval checkpoints
    approval_checkpoints = _build_approval_checkpoints(env_profile)

    # Build evidence requirements
    evidence_requirements = ["decision_trace", "test_results", "approval_records", "artifact_versions"]

    # Build change reassessment triggers
    change_triggers = ChangeReassessmentTriggers(
        architecture_delta=["new_external_integration", "new_trust_boundary",
                          "data_classification_change", "auth_flow_change"],
    )

    # Build remediation eligibility
    remediation_eligibility = AutonomousRemediationEligibility(
        default="human_required",
        rules=[RemediationRule(match="dependency_pin_update_nonprod", eligibility="auto_allowed")],
    )

    # Load active exceptions
    exceptions = []
    if apply_exceptions:
        exc_repo = ExceptionRepository(session)
        active = await exc_repo.get_active_by_project(project_id)
        exceptions = [e.exception_id for e in active]

    # Build promotion readiness (if evaluation exists)
    promotion_readiness = None
    try:
        from pearl.repositories.promotion_repo import PromotionEvaluationRepository

        eval_repo = PromotionEvaluationRepository(session)
        latest_eval = await eval_repo.get_latest_by_project(project_id)
        if latest_eval:
            promotion_readiness = {
                "current_environment": latest_eval.source_environment,
                "next_environment": latest_eval.target_environment,
                "status": latest_eval.status,
                "progress_pct": latest_eval.progress_pct,
                "passed_count": latest_eval.passed_count,
                "total_count": latest_eval.total_count,
                "blockers": latest_eval.blockers,
                "last_evaluated_at": latest_eval.evaluated_at.isoformat() if latest_eval.evaluated_at else None,
            }
    except Exception:
        pass  # Promotion tables may not exist yet

    # Build fairness requirements (if FRS exists)
    fairness_requirements = None
    try:
        from pearl.repositories.fairness_repo import FairnessRequirementsSpecRepository

        frs_repo = FairnessRequirementsSpecRepository(session)
        frs = await frs_repo.get_by_project(project_id)
        if frs:
            fairness_requirements = {
                "frs_id": frs.frs_id,
                "requirements": frs.requirements,
                "version": frs.version,
            }
    except Exception:
        pass  # Fairness tables may not exist yet

    package_id = generate_id("pkg_")
    app_id = spec.get("application", {}).get("app_id", "")

    package = CompiledContextPackage(
        schema_version="1.1",
        kind="PearlCompiledContextPackage",
        package_metadata=PackageMetadata(
            package_id=package_id,
            compiled_from=CompiledFrom(
                org_baseline_id=baseline.baseline_id,
                app_spec_id=app_id,
                environment_profile_id=env_profile.profile_id,
                remediation_overlay_id=None,
            ),
            integrity=compute_integrity({"project_id": project_id, "package_id": package_id}),
            compiler_version="1.1.0",
            merge_precedence_version="1.1",
        ),
        project_identity=ProjectIdentity(
            project_id=project_id,
            app_id=app_id,
            environment=env_profile.environment,
            delivery_stage=env_profile.delivery_stage,
            ai_enabled=project.ai_enabled,
        ),
        environment_profile={
            "risk_level": env_profile.risk_level,
            "approval_level": env_profile.approval_level,
        },
        autonomy_policy=autonomy_policy,
        security_requirements=security_requirements,
        responsible_ai_requirements=rai_requirements,
        iam_requirements=iam_requirements,
        network_requirements=network_requirements,
        data_handling_requirements=data_handling,
        tool_and_model_constraints=tool_constraints,
        required_tests=required_tests,
        approval_checkpoints=approval_checkpoints,
        evidence_requirements=evidence_requirements,
        change_reassessment_triggers=change_triggers,
        autonomous_remediation_eligibility=remediation_eligibility,
        exceptions=exceptions,
        promotion_readiness=promotion_readiness,
        fairness_requirements=fairness_requirements,
        traceability=TraceabilityRef(
            trace_id=trace_id,
            source_refs=[
                baseline.baseline_id,
                f"app_spec:{app_id}",
                env_profile.profile_id,
            ],
        ),
        references=[
            Reference(
                ref_id=f"api:/projects/{project_id}/compiled-package",
                kind="api",
                summary="Compiled package record",
            )
        ],
    )

    # Store compiled package
    pkg_repo = CompiledPackageRepository(session)
    pkg_data = package.model_dump(mode="json", exclude_none=True)
    await pkg_repo.create(
        package_id=package_id,
        project_id=project_id,
        environment=env_profile.environment,
        package_data=pkg_data,
        integrity=pkg_data.get("package_metadata", {}).get("integrity"),
    )

    return package


def _build_required_controls(defaults: dict, spec: dict) -> list[str]:
    controls = []
    if defaults.get("coding", {}).get("secure_coding_standard_required"):
        controls.extend(["authz_checks", "input_validation"])
    controls.extend(["tool_call_allowlisting", "audit_logging", "output_filtering"])
    return controls


def _build_prohibited_patterns(defaults: dict) -> list[str]:
    patterns = []
    if defaults.get("coding", {}).get("secret_hardcoding_forbidden"):
        patterns.append("hardcoded_secrets")
    if defaults.get("iam", {}).get("wildcard_permissions_forbidden_by_default"):
        patterns.append("wildcard_iam_permissions")
    if defaults.get("network", {}).get("outbound_connectivity_must_be_declared"):
        patterns.append("undeclared_external_egress")
    return patterns


def _build_approval_required_for(spec: dict) -> list[str]:
    return ["auth_flow_changes", "network_policy_changes", "data_retention_changes"]


def _build_rai_requirements(defaults: dict, spec: dict, ai_enabled: bool) -> ResponsibleAiRequirements | None:
    if not ai_enabled:
        return None
    rai = defaults.get("responsible_ai", {})
    return ResponsibleAiRequirements(
        transparency=Transparency(
            ai_disclosure_required=rai.get("ai_use_disclosure_required_for_user_facing", False),
            model_provenance_logging_required=rai.get("model_provenance_logging_required", False),
            explanation_metadata_required="basic",
        ),
        fairness=Fairness(
            review_required=rai.get("fairness_review_required_when_user_impact_is_material", False),
            monitoring_required=True,
        ),
        oversight=Oversight(
            human_review_required_for=["customer-impacting recommendations"] if rai.get("human_oversight_required_for_high_impact_actions") else [],
        ),
    )


def _build_network_requirements(spec: dict) -> NetworkRequirements:
    return NetworkRequirements(
        outbound_allowlist=["llm-gateway.internal", "telemetry.internal"],
        public_egress_forbidden=True,
    )


def _build_data_handling(spec: dict) -> DataHandlingRequirements | None:
    data = spec.get("data", {})
    prohibited = data.get("prohibited_in_model_context")
    if prohibited:
        return DataHandlingRequirements(prohibited_in_model_context=prohibited)
    return None


def _build_tool_constraints(env_profile) -> ToolAndModelConstraints:
    return ToolAndModelConstraints(
        allowed_tool_classes=["repo_edit", "tests", "static_analysis"],
        forbidden_tool_classes=["prod_admin"],
    )


def _build_required_tests(defaults: dict, ai_enabled: bool) -> RequiredTests:
    security = ["authz_negative_tests", "prompt_injection_guardrail_tests", "sensitive_data_leakage_tests"]
    rai = ["ai_disclosure_presence_test", "explanation_metadata_presence_test"] if ai_enabled else []
    functional = ["critical-path-smoke-test"]
    return RequiredTests(security=security, rai=rai, functional=functional)


def _build_approval_checkpoints(env_profile) -> list[ApprovalCheckpoint]:
    env = env_profile.environment
    level = env_profile.approval_level or "standard"

    checkpoints = []

    # All levels: deployment gate
    checkpoints.append(ApprovalCheckpoint(
        checkpoint_id="cp_deployment_gate",
        trigger="deployment_gate",
        required_roles=["platform_owner"],
        environment=env,
    ))

    if level in ("standard", "elevated", "high", "strict"):
        # Standard+: auth flow changes need security review
        checkpoints.append(ApprovalCheckpoint(
            checkpoint_id="cp_auth_flow_change",
            trigger="auth_flow_change",
            required_roles=["security_review", "platform_owner"],
            environment=env,
        ))

    if level in ("elevated", "high", "strict"):
        # Elevated+: network policy changes need review
        checkpoints.append(ApprovalCheckpoint(
            checkpoint_id="cp_network_policy_change",
            trigger="network_policy_change",
            required_roles=["security_review", "network_admin"],
            environment=env,
        ))

    if level in ("high", "strict"):
        # High+: exception creation and remediation execution need approval
        checkpoints.append(ApprovalCheckpoint(
            checkpoint_id="cp_exception_approval",
            trigger="exception",
            required_roles=["security_review", "platform_owner", "compliance_officer"],
            environment=env,
        ))
        checkpoints.append(ApprovalCheckpoint(
            checkpoint_id="cp_remediation_execution",
            trigger="remediation_execution",
            required_roles=["security_review"],
            environment=env,
        ))

    if level == "strict":
        # Strict: all deployment roles required, plus exec sign-off
        for cp in checkpoints:
            if "exec_sponsor" not in (cp.required_roles or []):
                cp.required_roles = (cp.required_roles or []) + ["exec_sponsor"]

    return checkpoints
