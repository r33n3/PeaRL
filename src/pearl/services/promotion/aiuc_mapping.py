# src/pearl/services/promotion/aiuc_mapping.py
"""Cross-framework → AIUC-1 control satisfaction mapping."""
from __future__ import annotations

FRAMEWORK_TO_AIUC1: dict[str, list[str]] = {
    # ── OWASP LLM Top 10 ──────────────────────────────────────────────────
    "owasp_llm/llm01_prompt_injection":       ["B005.1", "B005.2", "B005.4", "B005.5"],
    "owasp_llm/llm02_insecure_output_handling": ["C006.1", "C006.2", "B009.1", "B009.2"],
    "owasp_llm/llm03_training_data_poisoning": ["B001.1"],
    "owasp_llm/llm04_model_denial_of_service": ["B004.2"],
    "owasp_llm/llm05_supply_chain_vulnerabilities": ["B008.4"],
    "owasp_llm/llm06_sensitive_info_disclosure": ["A006.1", "A006.2"],
    "owasp_llm/llm07_insecure_plugin_design":  ["D003.1", "D003.2"],
    "owasp_llm/llm08_excessive_agency":        ["B006.1", "B006.2"],
    "owasp_llm/llm09_overreliance":            ["D001.1", "D001.2"],
    # ── NIST AI RMF ───────────────────────────────────────────────────────
    "nist_rmf/policy_defined":     ["C001.1"],
    "nist_rmf/roles_defined":      ["E004.1"],
    "nist_rmf/oversight_mechanism": ["C005.1", "C005.2", "C007.3"],
    "nist_rmf/risk_categorized":   ["C001.1", "C001.2"],
    "nist_rmf/threat_assessment":  ["B001.1", "B002.1"],
    "nist_rmf/bias_evaluated":     ["C003.3", "C003.4"],
    "nist_rmf/incident_plan":      ["E001.1", "E002.1"],
    "nist_rmf/rollback_plan":      ["E001.1"],
    "nist_rmf/monitoring_plan":    ["C008.1", "C008.2"],
    "nist_rmf/metrics_defined":    ["C008.1"],
    # ── MITRE ATLAS ───────────────────────────────────────────────────────
    "mitre_atlas/aml_t0051_supply_chain_compromise": ["B008.4"],
    "mitre_atlas/aml_t0043_craft_adversarial_data":  ["B001.1", "B002.4"],
    "mitre_atlas/aml_t0057_llm_prompt_injection":    ["B005.1"],
    "mitre_atlas/aml_t0012_valid_accounts":          ["B007.1", "B007.2"],
    "mitre_atlas/aml_t0031_erode_model_integrity":   ["B008.4"],
    # ── SLSA ──────────────────────────────────────────────────────────────
    "slsa/sbom_generated":    ["A006.3"],
    "slsa/artifact_signed":   ["B008.4"],
    "slsa/no_critical_cves":  ["B004.4"],
    "slsa/dependency_review": ["B004.4"],
    # ── NIST SSDF ─────────────────────────────────────────────────────────
    "ssdf/pw1_security_design":    ["B001.2"],
    "ssdf/pw6_code_review":        ["C002.2"],
    "ssdf/pw7_security_testing":   ["C002.3"],
    "ssdf/pw8_vulnerability_scanning": ["B004.4"],
    "ssdf/rv1_disclosure_process": ["B003.1", "B003.2"],
    "ssdf/rv3_remediation":        ["B004.4"],
    # ── OWASP Web Top 10 ──────────────────────────────────────────────────
    "owasp_web/a01_broken_access_control":    ["B007.1"],
    "owasp_web/a02_cryptographic_failures":   ["B008.2"],
    "owasp_web/a07_auth_failures":            ["B007.1", "B007.2"],
    "owasp_web/a08_software_integrity_failures": ["B008.4"],
}

FINDING_CATEGORY_TO_AIUC1_BLOCKED: dict[str, list[str]] = {
    "prompt_injection":      ["B005.1", "B005.2"],
    "insecure_output":       ["C006.1", "B009.1"],
    "pii_exposure":          ["A006.1", "A006.2"],
    "data_leak":             ["A006.1", "A006.3"],
    "supply_chain":          ["B008.4"],
    "access_control":        ["B007.1", "B006.1"],
    "behavioral_drift":      ["C008.1", "C005.1"],
    "drift_acute":           ["C008.1", "C005.1"],
    "hardcoded_secret":      ["B007.1"],
    "excessive_agency":      ["B006.1", "D003.1"],
    "hallucination":         ["D001.1"],
    "tool_misuse":           ["D003.1"],
    "model_theft":           ["B008.1"],
    "insecure_plugin":       ["D003.1", "D003.2"],
    "training_data_poison":  ["B001.1"],
}

AIUC1_MANDATORY_PILOT: list[str] = [
    "B001.1", "B001.2", "B002.1", "B004.2", "B004.4",
    "B005.1", "B005.2", "B006.1", "B006.2", "B007.1",
    "B008.4", "C001.1", "C002.2", "C002.3", "C003.3",
    "C005.1", "C005.2", "C006.1", "C007.3", "C008.1",
    "A006.1", "A006.2", "D003.1", "D003.2",
    "E001.1", "E004.1", "E015.1", "E016.1",
]

AIUC1_DIRECT_ATTESTATION_HINT: dict[str, str] = {
    "A006.1": "submit evidence_type='attestation' with control_id='aiuc1/A006.1' documenting PII detection/filtering implementation",
    "A006.2": "submit evidence_type='attestation' with control_id='aiuc1/A006.2' documenting PII access controls",
    "D003.1": "submit evidence_type='attestation' with control_id='aiuc1/D003.1' documenting tool call authorization validation",
    "E015.1": "submit evidence_type='attestation' with control_id='aiuc1/E015.1' documenting logging implementation",
    "E016.1": "submit evidence_type='attestation' with control_id='aiuc1/E016.1' documenting AI disclosure to users",
}

AIUC1_SATISFACTION_HINT: dict[str, str] = {
    "B001.1": "attest owasp_llm/llm03_training_data_poisoning OR mitre_atlas/aml_t0043_craft_adversarial_data",
    "B001.2": "attest ssdf/pw1_security_design",
    "B002.1": "attest nist_rmf/threat_assessment",
    "B004.2": "attest owasp_llm/llm04_model_denial_of_service",
    "B004.4": "pass slsa/no_critical_cves scan OR attest ssdf/pw8_vulnerability_scanning",
    "B005.1": "pass owasp_llm/llm01_prompt_injection scan OR attest mitre_atlas/aml_t0057",
    "B005.2": "attest owasp_llm/llm01_prompt_injection",
    "B006.1": "attest owasp_llm/llm08_excessive_agency",
    "B006.2": "attest owasp_llm/llm08_excessive_agency",
    "B007.1": "pass owasp_web/a01_broken_access_control scan OR attest mitre_atlas/aml_t0012_valid_accounts",
    "B008.4": "submit evidence_type='artifact_signed' OR attest slsa/artifact_signed",
    "C001.1": "attest nist_rmf/policy_defined OR nist_rmf/risk_categorized",
    "C002.2": "attest ssdf/pw6_code_review",
    "C002.3": "attest ssdf/pw7_security_testing",
    "C003.3": "attest nist_rmf/bias_evaluated",
    "C005.1": "attest nist_rmf/oversight_mechanism (PeaRL deployment satisfies this)",
    "C005.2": "attest nist_rmf/oversight_mechanism (PeaRL deployment satisfies this)",
    "C006.1": "attest owasp_llm/llm02_insecure_output_handling",
    "C007.3": "attest nist_rmf/oversight_mechanism",
    "C008.1": "attest nist_rmf/monitoring_plan OR nist_rmf/metrics_defined",
    **AIUC1_DIRECT_ATTESTATION_HINT,
}


def aiuc_controls_satisfied_by_framework(framework: str, control_id: str) -> list[str]:
    """Return AIUC-1 control IDs satisfied by passing the given framework control."""
    key = f"{framework}/{control_id}"
    return list(FRAMEWORK_TO_AIUC1.get(key, []))


def aiuc_controls_blocked_by_findings(finding_categories: list[str]) -> set[str]:
    """Return AIUC-1 control IDs blocked by any of the given open finding categories."""
    blocked: set[str] = set()
    for cat in finding_categories:
        blocked.update(FINDING_CATEGORY_TO_AIUC1_BLOCKED.get(cat, []))
    return blocked


def compute_aiuc_compliance(ctx, mandatory_controls: list[str]) -> dict:
    """Derive AIUC-1 compliance status from eval context."""
    satisfied: set[str] = set()

    for ev in ctx.evidence_packages:
        data = getattr(ev, "evidence_data", None) or {}
        ctrl = data.get("control_id", "")
        if not ctrl:
            continue
        if ctrl.startswith("aiuc1/"):
            short = ctrl[len("aiuc1/"):]
            satisfied.add(short)
        elif "/" in ctrl:
            satisfied.update(FRAMEWORK_TO_AIUC1.get(ctrl, []))

    open_categories = [f.category for f in ctx.open_findings if getattr(f, "status", "open") == "open"]
    blocked = aiuc_controls_blocked_by_findings(open_categories)

    net_satisfied = satisfied - blocked
    mandatory_set = set(mandatory_controls)
    outstanding = sorted(mandatory_set - net_satisfied)
    satisfied_mandatory = mandatory_set & net_satisfied
    score_pct = (len(satisfied_mandatory) / len(mandatory_set) * 100) if mandatory_set else 100.0

    hints = {ctrl: AIUC1_SATISFACTION_HINT.get(ctrl, f"attest aiuc1/{ctrl}") for ctrl in outstanding}

    return {
        "satisfied": satisfied,
        "blocked": blocked,
        "net_satisfied": net_satisfied,
        "outstanding": outstanding,
        "score_pct": round(score_pct, 1),
        "hints": hints,
        "mandatory_count": len(mandatory_set),
        "satisfied_count": len(satisfied_mandatory),
    }
