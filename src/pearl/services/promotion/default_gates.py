"""Default promotion gate definitions for the 4 environment transitions."""

from pearl.models.enums import GateRuleType


def _rule(rule_type: str, description: str, ai_only: bool = False, threshold: float | None = None, **kwargs):
    """Helper to build a gate rule definition dict."""
    r = {
        "rule_id": f"rule_{rule_type}",
        "rule_type": rule_type,
        "description": description,
        "required": True,
        "ai_only": ai_only,
    }
    if threshold is not None:
        r["threshold"] = threshold
    if kwargs:
        r["parameters"] = kwargs
    return r


# ─── sandbox → dev (8 rules) ──────────────────────────────────

SANDBOX_TO_DEV = {
    "gate_id": "gate_sandbox_to_dev",
    "source_environment": "sandbox",
    "target_environment": "dev",
    "rules": [
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered in PeaRL"),
        _rule(GateRuleType.CLAUDE_MD_GOVERNANCE_PRESENT, "PeaRL governance block must be present and confirmed in CLAUDE.md"),
        _rule(GateRuleType.ORG_BASELINE_ATTACHED, "Organization security baseline must be attached"),
        _rule(GateRuleType.APP_SPEC_DEFINED, "Application specification must be defined"),
        _rule(GateRuleType.NO_HARDCODED_SECRETS, "No hardcoded secrets in codebase"),
        _rule(GateRuleType.UNIT_TESTS_EXIST, "Unit tests must exist"),
        _rule(GateRuleType.FAIRNESS_CASE_DEFINED, "Fairness case must be defined for AI projects", ai_only=True),
        _rule(GateRuleType.MODEL_CARD_DOCUMENTED, "Model card must be documented for AI projects", ai_only=True),
    ],
}

# ─── dev → preprod (merged from dev→pilot + pilot→preprod) ───────

DEV_TO_PREPROD = {
    "gate_id": "gate_dev_to_preprod",
    "source_environment": "dev",
    "target_environment": "preprod",
    "rules": [
        # Core rules
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered in PeaRL"),
        _rule(GateRuleType.ORG_BASELINE_ATTACHED, "Organization security baseline must be attached"),
        _rule(GateRuleType.APP_SPEC_DEFINED, "Application specification must be defined"),
        _rule(GateRuleType.NO_HARDCODED_SECRETS, "No hardcoded secrets in codebase"),
        _rule(GateRuleType.UNIT_TESTS_EXIST, "Unit tests must exist"),
        _rule(GateRuleType.SECURITY_BASELINE_TESTS, "Security baseline tests must pass"),
        _rule(GateRuleType.CRITICAL_FINDINGS_ZERO, "Zero critical-severity findings"),
        _rule(GateRuleType.DATA_CLASSIFICATIONS_DOCUMENTED, "Data classifications must be documented"),
        _rule(GateRuleType.IAM_ROLES_DEFINED, "IAM roles and permissions must be defined"),
        _rule(GateRuleType.HIGH_FINDINGS_ZERO, "Zero high-severity findings"),
        _rule(GateRuleType.NETWORK_BOUNDARIES_DECLARED, "Network boundaries declared"),
        _rule(GateRuleType.INTEGRATION_TEST_COVERAGE, "Integration test coverage >= 60%", threshold=60),
        _rule(GateRuleType.SECURITY_REVIEW_APPROVAL, "Security review approval required"),
        # AI-specific
        _rule(GateRuleType.FAIRNESS_CASE_DEFINED, "Fairness case must be defined", ai_only=True),
        _rule(GateRuleType.AI_SCAN_COMPLETED, "PeaRL AI security scan must be completed", ai_only=True),
        _rule(GateRuleType.NO_PROMPT_INJECTION, "Zero prompt injection findings", ai_only=True),
        _rule(GateRuleType.REQUIRED_ANALYZERS_COMPLETED, "Required AI analyzers must have run", ai_only=True),
        _rule(GateRuleType.FAIRNESS_REQUIREMENTS_MET, "Fairness requirements must be met", ai_only=True),
        _rule(GateRuleType.GUARDRAILS_VERIFIED, "Guardrails verified (0 findings)", ai_only=True),
        _rule(GateRuleType.NO_PII_LEAKAGE, "Zero PII leakage findings", ai_only=True),
        _rule(GateRuleType.FAIRNESS_ATTESTATION_SIGNED, "Fairness attestation signed", ai_only=True),
        _rule(GateRuleType.FAIRNESS_HARD_BLOCKS_CLEAR, "No fairness hard blocks", ai_only=True),
        _rule(GateRuleType.RAI_EVAL_COMPLETED, "RAI evaluation completed", ai_only=True),
        _rule(GateRuleType.COMPLIANCE_SCORE_THRESHOLD, "Compliance score >= 80%", ai_only=True, threshold=80.0),
        _rule(GateRuleType.SECURITY_REVIEW_CLEAR, "All /security-review findings addressed"),
        _rule(GateRuleType.GUARDRAIL_COVERAGE, "Guardrail coverage adequate", ai_only=True),
    ],
}

# ─── preprod → prod (25 rules) ────────────────────────────────

PREPROD_TO_PROD = {
    "gate_id": "gate_preprod_to_prod",
    "source_environment": "preprod",
    "target_environment": "prod",
    "rules": [
        # Core rules
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered"),
        _rule(GateRuleType.ORG_BASELINE_ATTACHED, "Org baseline must be attached"),
        _rule(GateRuleType.APP_SPEC_DEFINED, "App spec must be defined"),
        _rule(GateRuleType.NO_HARDCODED_SECRETS, "No hardcoded secrets"),
        _rule(GateRuleType.UNIT_TESTS_EXIST, "Unit tests must exist"),
        _rule(GateRuleType.SECURITY_BASELINE_TESTS, "Security baseline tests must pass"),
        _rule(GateRuleType.CRITICAL_FINDINGS_ZERO, "Zero critical findings"),
        _rule(GateRuleType.HIGH_FINDINGS_ZERO, "Zero high findings"),
        _rule(GateRuleType.DATA_CLASSIFICATIONS_DOCUMENTED, "Data classifications documented"),
        _rule(GateRuleType.IAM_ROLES_DEFINED, "IAM roles defined"),
        _rule(GateRuleType.NETWORK_BOUNDARIES_DECLARED, "Network boundaries declared"),
        _rule(GateRuleType.SECURITY_REVIEW_APPROVAL, "Security review approval"),
        # New for preprod → prod
        _rule(GateRuleType.UNIT_TEST_COVERAGE, "Unit test coverage >= 80%", threshold=80),
        _rule(GateRuleType.ALL_CONTROLS_VERIFIED, "All security controls verified"),
        _rule(GateRuleType.EXEC_SPONSOR_APPROVAL, "Executive sponsor approval required"),
        _rule(GateRuleType.RESIDUAL_RISK_REPORT, "Residual risk report generated"),
        _rule(GateRuleType.READ_ONLY_AUTONOMY, "Production autonomy mode verified"),
        # AI-specific
        _rule(GateRuleType.AI_SCAN_COMPLETED, "PeaRL AI security scan completed", ai_only=True),
        _rule(GateRuleType.OWASP_LLM_TOP10_CLEAR, "OWASP LLM Top 10 clear", ai_only=True),
        _rule(GateRuleType.AI_RISK_ACCEPTABLE, "AI scan risk below threshold", ai_only=True, threshold=7.0),
        _rule(GateRuleType.COMPREHENSIVE_AI_SCAN, "Comprehensive AI scan with verdicts", ai_only=True),
        _rule(GateRuleType.FAIRNESS_DRIFT_ACCEPTABLE, "Fairness drift within limits", ai_only=True, threshold=0.1),
        _rule(GateRuleType.FAIRNESS_EXCEPTIONS_CONTROLLED, "Fairness exceptions have controls", ai_only=True),
        _rule(GateRuleType.FAIRNESS_CONTEXT_RECEIPT_VALID, "Agent fairness context receipt on file", ai_only=True),
        _rule(GateRuleType.FAIRNESS_POLICY_DEPLOYED, "Fairness policy fully deployed", ai_only=True),
        _rule(GateRuleType.COMPLIANCE_SCORE_THRESHOLD, "Compliance score >= 90% for production", ai_only=True, threshold=90.0),
        _rule(GateRuleType.REQUIRED_ANALYZERS_COMPLETED, "All required AI analyzers completed", ai_only=True),
        _rule(GateRuleType.SECURITY_REVIEW_CLEAR, "All /security-review findings addressed"),
        _rule(GateRuleType.GUARDRAIL_COVERAGE, "Guardrail coverage complete for production", ai_only=True),
    ],
}


DEFAULT_GATES = [SANDBOX_TO_DEV, DEV_TO_PREPROD, PREPROD_TO_PROD]

# Default promotion pipeline matching the 3-gate chain above
DEFAULT_PIPELINE = {
    "pipeline_id": "pipe_default",
    "name": "Default Chain",
    "description": "Standard 4-stage promotion chain: sandbox → dev → preprod → prod",
    "is_default": True,
    "stages": [
        {"key": "sandbox", "label": "Sandbox", "description": "Initial sandbox environment", "order": 0},
        {"key": "dev", "label": "Dev", "description": "Active development environment", "order": 1},
        {"key": "preprod", "label": "Preprod", "description": "Pre-production staging environment", "order": 2},
        {"key": "prod", "label": "Prod", "description": "Live production environment", "order": 3},
    ],
}


async def seed_default_gates(session) -> int:
    """Seed default promotion gates and pipeline (idempotent).

    Returns the number of gates created (0 if already exist).
    """
    from pearl.repositories.pipeline_repo import PromotionPipelineRepository
    from pearl.repositories.promotion_repo import PromotionGateRepository

    gate_repo = PromotionGateRepository(session)
    created = 0

    for gate_def in DEFAULT_GATES:
        existing = await gate_repo.get(gate_def["gate_id"])
        if not existing:
            await gate_repo.create(
                gate_id=gate_def["gate_id"],
                source_environment=gate_def["source_environment"],
                target_environment=gate_def["target_environment"],
                project_id=None,
                rules=gate_def["rules"],
            )
            created += 1

    # Seed the default pipeline
    pipeline_repo = PromotionPipelineRepository(session)
    existing_pipeline = await pipeline_repo.get("pipe_default")
    if not existing_pipeline:
        await pipeline_repo.create(
            pipeline_id=DEFAULT_PIPELINE["pipeline_id"],
            name=DEFAULT_PIPELINE["name"],
            description=DEFAULT_PIPELINE["description"],
            is_default=DEFAULT_PIPELINE["is_default"],
            stages=DEFAULT_PIPELINE["stages"],
            project_id=None,
        )

    return created


async def seed_demo_data(session) -> None:
    """Seed DEMO org baseline + Demo-BU1 + Demo-BU2 (idempotent)."""
    from sqlalchemy import select
    from pearl.db.models.org_baseline import OrgBaselineRow
    from pearl.db.models.business_unit import BusinessUnitRow
    from pearl.db.models.org import OrgRow
    from pearl.scanning.baseline_package import ESSENTIAL_BASELINE

    # Seed the default org (required FK for BUs and baselines)
    existing_org = (await session.execute(
        select(OrgRow).where(OrgRow.org_id == "org_default")
    )).scalar_one_or_none()
    if not existing_org:
        session.add(OrgRow(
            org_id="org_default",
            name="DEMO",
            slug="demo",
            settings={},
        ))
        await session.flush()

    # Rename any existing org-wide baseline to "DEMO" (fixes "benderbox dev org" display)
    org_wide = await session.execute(
        select(OrgBaselineRow)
        .where(OrgBaselineRow.project_id.is_(None))
        .where(OrgBaselineRow.bu_id.is_(None))
        .limit(1)
    )
    existing_org = org_wide.scalar_one_or_none()
    if existing_org and existing_org.org_name != "DEMO":
        existing_org.org_name = "DEMO"
        return  # already have an org baseline, just renamed it

    # Seed org-wide DEMO baseline if absent
    existing_baseline = (await session.execute(
        select(OrgBaselineRow).where(OrgBaselineRow.baseline_id == "orgb_demo")
    )).scalar_one_or_none()

    if not existing_baseline:
        demo_baseline = OrgBaselineRow(
            baseline_id="orgb_demo",
            project_id=None,
            bu_id=None,
            org_id="org_default",
            org_name="DEMO",
            defaults=ESSENTIAL_BASELINE["defaults"],
            schema_version="1.1",
        )
        session.add(demo_baseline)

    # Seed Demo-BU1 (inherits org — no custom baseline row)
    bu1 = (await session.execute(
        select(BusinessUnitRow).where(BusinessUnitRow.bu_id == "bu_demo_1")
    )).scalar_one_or_none()
    if not bu1:
        session.add(BusinessUnitRow(
            bu_id="bu_demo_1",
            org_id="org_default",
            name="Demo-BU1",
            description="Primary business unit — inherits DEMO org baseline",
            framework_selections=["aiuc1"],
            additional_guardrails={},
        ))

    # Seed Demo-BU2 (custom baseline with stricter security domain)
    bu2 = (await session.execute(
        select(BusinessUnitRow).where(BusinessUnitRow.bu_id == "bu_demo_2")
    )).scalar_one_or_none()
    if not bu2:
        session.add(BusinessUnitRow(
            bu_id="bu_demo_2",
            org_id="org_default",
            name="Demo-BU2",
            description="Subsidiary business unit — custom security baseline",
            framework_selections=["aiuc1", "owasp_llm"],
            additional_guardrails={},
        ))

    # Seed Demo-BU2 custom baseline (all security controls enabled)
    existing_bu2_baseline = (await session.execute(
        select(OrgBaselineRow).where(OrgBaselineRow.baseline_id == "orgb_demo_bu2")
    )).scalar_one_or_none()
    if not existing_bu2_baseline:
        import copy
        bu2_defaults = copy.deepcopy(ESSENTIAL_BASELINE["defaults"])
        # Tighten security domain — enable all B controls
        if "security" in bu2_defaults:
            bu2_defaults["security"] = {k: True for k in bu2_defaults["security"]}
        session.add(OrgBaselineRow(
            baseline_id="orgb_demo_bu2",
            project_id=None,
            bu_id="bu_demo_2",
            org_id="org_default",
            org_name="DEMO",
            defaults=bu2_defaults,
            schema_version="1.1",
        ))
