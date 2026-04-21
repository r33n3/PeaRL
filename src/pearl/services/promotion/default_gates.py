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


# ─── pilot → dev ──────────────────────────────────────────────
# Experimental → active development. Governance, baseline, and AI scan checks.

PILOT_TO_DEV = {
    "gate_id": "gate_5730ef26ca8c46e9",
    "source_environment": "pilot",
    "target_environment": "dev",
    "rules": [
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered in PeaRL"),
        _rule(GateRuleType.CLAUDE_MD_GOVERNANCE_PRESENT, "PeaRL governance block must be present in CLAUDE.md"),
        _rule(GateRuleType.ORG_BASELINE_ATTACHED, "Organization security baseline must be attached"),
        _rule(GateRuleType.APP_SPEC_DEFINED, "Application specification must be defined"),
        _rule(GateRuleType.NO_HARDCODED_SECRETS, "No hardcoded secrets in codebase"),
        _rule(GateRuleType.UNIT_TESTS_EXIST, "Unit tests must exist"),
        _rule(GateRuleType.AI_SCAN_COMPLETED, "AI security scan must be completed", ai_only=True),
        _rule(GateRuleType.FAIRNESS_CASE_DEFINED, "Fairness case must be defined", ai_only=True),
        _rule(GateRuleType.MODEL_CARD_DOCUMENTED, "Model card must be documented", ai_only=True),
    ],
}

# ─── dev → prod ────────────────────────────────────────────────
# Full governance gate before production. Human approval required.

DEV_TO_PROD = {
    "gate_id": "gate_ce6c49cb2a3d48bf",
    "source_environment": "dev",
    "target_environment": "prod",
    "rules": [
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered in PeaRL"),
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
        _rule(GateRuleType.SECURITY_REVIEW_APPROVAL, "Security review approval required"),
        _rule(GateRuleType.UNIT_TEST_COVERAGE, "Unit test coverage >= 80%", threshold=80),
        _rule(GateRuleType.ALL_CONTROLS_VERIFIED, "All security controls verified"),
        _rule(GateRuleType.EXEC_SPONSOR_APPROVAL, "Executive sponsor approval required"),
        _rule(GateRuleType.RESIDUAL_RISK_REPORT, "Residual risk report generated"),
        _rule(GateRuleType.READ_ONLY_AUTONOMY, "Production autonomy mode verified"),
        _rule(GateRuleType.AI_SCAN_COMPLETED, "AI security scan completed", ai_only=True),
        _rule(GateRuleType.OWASP_LLM_TOP10_CLEAR, "OWASP LLM Top 10 clear", ai_only=True),
        _rule(GateRuleType.AI_RISK_ACCEPTABLE, "AI scan risk below threshold", ai_only=True, threshold=7.0),
        _rule(GateRuleType.COMPREHENSIVE_AI_SCAN, "Comprehensive AI scan with verdicts", ai_only=True),
        _rule(GateRuleType.LITELLM_COMPLIANCE, "LiteLLM proxy must be configured and compliant", ai_only=True),
        _rule(GateRuleType.FACTORY_RUN_SUMMARY_PRESENT, "Factory run summary present with no anomaly flags", ai_only=True),
        _rule(GateRuleType.SONARQUBE_QUALITY_GATE, "SonarQube quality gate must pass (OK)"),
        _rule(GateRuleType.SNYK_OPEN_HIGH_CRITICAL, "Snyk SCA: no open HIGH/CRITICAL vulnerabilities"),
    ],
}


DEFAULT_GATES = [PILOT_TO_DEV, DEV_TO_PROD]

# Default promotion pipeline: pilot → dev → prod
DEFAULT_PIPELINE = {
    "pipeline_id": "pipe_default",
    "name": "Default Chain",
    "description": "Standard 3-stage promotion chain: pilot → dev → prod",
    "is_default": True,
    "stages": [
        {"key": "pilot", "label": "Pilot", "description": "Non-guardrailed experimental environment", "order": 0},
        {"key": "dev", "label": "Dev", "description": "Active development environment", "order": 1},
        {"key": "prod", "label": "Prod", "description": "Live production environment", "order": 2},
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

    # Remove legacy gates that no longer match the pipeline
    _legacy_gate_ids = ["gate_sandbox_to_dev", "gate_dev_to_preprod", "gate_preprod_to_prod"]
    for legacy_id in _legacy_gate_ids:
        legacy = await gate_repo.get(legacy_id)
        if legacy:
            await session.delete(legacy)

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
        else:
            # Always sync rules so new rule types added to code land in the DB
            existing.rules = gate_def["rules"]

    # Seed the default pipeline — only if no default exists yet (don't override user config)
    pipeline_repo = PromotionPipelineRepository(session)
    existing_pipeline = await pipeline_repo.get("pipe_default")
    if not existing_pipeline:
        current_default = await pipeline_repo.get_default()
        await pipeline_repo.create(
            pipeline_id=DEFAULT_PIPELINE["pipeline_id"],
            name=DEFAULT_PIPELINE["name"],
            description=DEFAULT_PIPELINE["description"],
            is_default=current_default is None,  # only default if nothing else is
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

