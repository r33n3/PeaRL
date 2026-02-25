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


# ─── sandbox → dev (7 rules) ──────────────────────────────────

SANDBOX_TO_DEV = {
    "gate_id": "gate_sandbox_to_dev",
    "source_environment": "sandbox",
    "target_environment": "dev",
    "rules": [
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered in PeaRL"),
        _rule(GateRuleType.ORG_BASELINE_ATTACHED, "Organization security baseline must be attached"),
        _rule(GateRuleType.APP_SPEC_DEFINED, "Application specification must be defined"),
        _rule(GateRuleType.NO_HARDCODED_SECRETS, "No hardcoded secrets in codebase"),
        _rule(GateRuleType.UNIT_TESTS_EXIST, "Unit tests must exist"),
        _rule(GateRuleType.FAIRNESS_CASE_DEFINED, "Fairness case must be defined for AI projects", ai_only=True),
        _rule(GateRuleType.MODEL_CARD_DOCUMENTED, "Model card must be documented for AI projects", ai_only=True),
    ],
}

# ─── dev → pilot (13 rules) ───────────────────────────────────

DEV_TO_PILOT = {
    "gate_id": "gate_dev_to_pilot",
    "source_environment": "dev",
    "target_environment": "pilot",
    "rules": [
        # Carry forward from sandbox → dev
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered in PeaRL"),
        _rule(GateRuleType.ORG_BASELINE_ATTACHED, "Organization security baseline must be attached"),
        _rule(GateRuleType.APP_SPEC_DEFINED, "Application specification must be defined"),
        _rule(GateRuleType.NO_HARDCODED_SECRETS, "No hardcoded secrets in codebase"),
        _rule(GateRuleType.UNIT_TESTS_EXIST, "Unit tests must exist"),
        # New for dev → pilot
        _rule(GateRuleType.SECURITY_BASELINE_TESTS, "Security baseline tests must pass"),
        _rule(GateRuleType.CRITICAL_FINDINGS_ZERO, "Zero critical-severity findings"),
        _rule(GateRuleType.DATA_CLASSIFICATIONS_DOCUMENTED, "Data classifications must be documented"),
        _rule(GateRuleType.IAM_ROLES_DEFINED, "IAM roles and permissions must be defined"),
        # AI-specific
        _rule(GateRuleType.FAIRNESS_CASE_DEFINED, "Fairness case must be defined", ai_only=True),
        _rule(GateRuleType.MASS_SCAN_COMPLETED, "MASS security scan must be completed", ai_only=True),
        _rule(GateRuleType.NO_PROMPT_INJECTION, "Zero prompt injection findings", ai_only=True),
        _rule(GateRuleType.REQUIRED_ANALYZERS_COMPLETED, "Required AI analyzers must have run", ai_only=True),
        _rule(GateRuleType.FAIRNESS_REQUIREMENTS_MET, "Fairness requirements must be met", ai_only=True),
    ],
}

# ─── pilot → preprod (19 rules) ───────────────────────────────

PILOT_TO_PREPROD = {
    "gate_id": "gate_pilot_to_preprod",
    "source_environment": "pilot",
    "target_environment": "preprod",
    "rules": [
        # Core rules
        _rule(GateRuleType.PROJECT_REGISTERED, "Project must be registered"),
        _rule(GateRuleType.ORG_BASELINE_ATTACHED, "Org baseline must be attached"),
        _rule(GateRuleType.APP_SPEC_DEFINED, "App spec must be defined"),
        _rule(GateRuleType.NO_HARDCODED_SECRETS, "No hardcoded secrets"),
        _rule(GateRuleType.UNIT_TESTS_EXIST, "Unit tests must exist"),
        _rule(GateRuleType.SECURITY_BASELINE_TESTS, "Security baseline tests must pass"),
        _rule(GateRuleType.CRITICAL_FINDINGS_ZERO, "Zero critical findings"),
        _rule(GateRuleType.DATA_CLASSIFICATIONS_DOCUMENTED, "Data classifications documented"),
        _rule(GateRuleType.IAM_ROLES_DEFINED, "IAM roles defined"),
        # New for pilot → preprod
        _rule(GateRuleType.HIGH_FINDINGS_ZERO, "Zero high-severity findings"),
        _rule(GateRuleType.NETWORK_BOUNDARIES_DECLARED, "Network boundaries declared"),
        _rule(GateRuleType.INTEGRATION_TEST_COVERAGE, "Integration test coverage >= 60%", threshold=60),
        _rule(GateRuleType.SECURITY_REVIEW_APPROVAL, "Security review approval required"),
        # AI-specific
        _rule(GateRuleType.MASS_SCAN_COMPLETED, "MASS scan completed", ai_only=True),
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
        _rule(GateRuleType.MASS_SCAN_COMPLETED, "MASS scan completed", ai_only=True),
        _rule(GateRuleType.OWASP_LLM_TOP10_CLEAR, "OWASP LLM Top 10 clear", ai_only=True),
        _rule(GateRuleType.MASS_RISK_ACCEPTABLE, "MASS risk below threshold", ai_only=True, threshold=7.0),
        _rule(GateRuleType.COMPREHENSIVE_MASS_SCAN, "Comprehensive MASS scan with verdicts", ai_only=True),
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


DEFAULT_GATES = [SANDBOX_TO_DEV, DEV_TO_PILOT, PILOT_TO_PREPROD, PREPROD_TO_PROD]


async def seed_default_gates(session) -> int:
    """Seed default promotion gates (idempotent).

    Returns the number of gates created (0 if already exist).
    """
    from pearl.repositories.promotion_repo import PromotionGateRepository

    repo = PromotionGateRepository(session)
    created = 0

    for gate_def in DEFAULT_GATES:
        existing = await repo.get(gate_def["gate_id"])
        if not existing:
            await repo.create(
                gate_id=gate_def["gate_id"],
                source_environment=gate_def["source_environment"],
                target_environment=gate_def["target_environment"],
                project_id=None,
                rules=gate_def["rules"],
            )
            created += 1

    return created
