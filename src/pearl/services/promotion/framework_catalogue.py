"""Python mirror of frameworkControls.ts — maps framework keys to derived requirements.

Each entry: {"control_id": str, "applies_to_transitions": list[str],
             "requirement_level": "mandatory"|"recommended", "evidence_type": str}
"""

# Transition helpers
_ALL = ["*"]
_DEV_UP = ["dev->preprod", "preprod->prod"]
_SANDBOX_UP = ["sandbox->dev"]
_PREPROD_UP = ["preprod->prod"]


def _attestation(cid, transitions, level="recommended"):
    return {"control_id": cid, "applies_to_transitions": transitions, "requirement_level": level, "evidence_type": "attestation"}


def _scan(cid, transitions, level="mandatory"):
    return {"control_id": cid, "applies_to_transitions": transitions, "requirement_level": level, "evidence_type": "scan_result"}


def _artifact(cid, transitions, level="mandatory"):
    return {"control_id": cid, "applies_to_transitions": transitions, "requirement_level": level, "evidence_type": "artifact"}


def _derived(cid, transitions, level="recommended"):
    return {"control_id": cid, "applies_to_transitions": transitions, "requirement_level": level, "evidence_type": "derived"}


# AIUC-1 controls by category
# security (B) + safety (C) + accountability (E) → mandatory for dev->preprod+
# other categories (A, D, F) → recommended for sandbox->dev

_AIUC1_SECURITY = [
    _attestation("b001_1_adversarial_testing_report", _DEV_UP, "mandatory"),
    _attestation("b001_2_security_program_integration", _DEV_UP, "mandatory"),
    _attestation("b002_1_adversarial_input_detection_alerting", _DEV_UP, "mandatory"),
    _attestation("b002_2_adversarial_incident_response", _DEV_UP, "mandatory"),
    _attestation("b002_3_detection_config_updates", _DEV_UP, "mandatory"),
    _attestation("b002_4_preprocessing_adversarial_detection", _DEV_UP, "mandatory"),
    _attestation("b002_5_ai_security_alerts", _DEV_UP, "mandatory"),
    _attestation("b003_1_technical_disclosure_guidelines", _DEV_UP, "mandatory"),
    _attestation("b003_2_public_disclosure_approval_records", _DEV_UP, "mandatory"),
    _attestation("b004_1_anomalous_usage_detection", _DEV_UP, "mandatory"),
    _attestation("b004_2_rate_limits", _DEV_UP, "mandatory"),
    _attestation("b004_3_external_pentest_ai_endpoints", _DEV_UP, "mandatory"),
    _attestation("b004_4_vulnerability_remediation", _DEV_UP, "mandatory"),
    _attestation("b005_1_input_filtering", _DEV_UP, "mandatory"),
    _attestation("b005_2_input_moderation_approach", _DEV_UP, "mandatory"),
    _attestation("b005_3_warning_for_blocked_inputs", _DEV_UP, "mandatory"),
    _attestation("b005_4_input_filtering_logs", _DEV_UP, "mandatory"),
    _attestation("b005_5_input_filter_performance", _DEV_UP, "mandatory"),
    _attestation("b006_1_agent_service_access_restrictions", _DEV_UP, "mandatory"),
    _attestation("b006_2_agent_security_monitoring_alerting", _DEV_UP, "mandatory"),
    _attestation("b007_1_user_access_controls", _DEV_UP, "mandatory"),
    _attestation("b007_2_access_reviews", _DEV_UP, "mandatory"),
    _attestation("b008_1_model_access_controls", _DEV_UP, "mandatory"),
    _attestation("b008_2_api_deployment_security", _DEV_UP, "mandatory"),
    _attestation("b008_3_model_hosting_security", _DEV_UP, "mandatory"),
    _attestation("b008_4_model_integrity_verification", _DEV_UP, "mandatory"),
    _attestation("b009_1_output_volume_limits", _DEV_UP, "mandatory"),
    _attestation("b009_2_user_output_notices", _DEV_UP, "mandatory"),
    _attestation("b009_3_output_precision_controls", _DEV_UP, "mandatory"),
]

_AIUC1_SAFETY = [
    _attestation("c001_1_risk_taxonomy", _DEV_UP, "mandatory"),
    _attestation("c001_2_risk_taxonomy_reviews", _DEV_UP, "mandatory"),
    _attestation("c002_1_pre_deployment_test_approval", _DEV_UP, "mandatory"),
    _attestation("c002_2_sdlc_integration", _DEV_UP, "mandatory"),
    _attestation("c002_3_vulnerability_scan_results", _DEV_UP, "mandatory"),
    _attestation("c003_1_harmful_output_filtering", _DEV_UP, "mandatory"),
    _attestation("c003_2_guardrails_for_high_risk_advice", _DEV_UP, "mandatory"),
    _attestation("c003_3_guardrails_for_biased_outputs", _DEV_UP, "mandatory"),
    _attestation("c003_4_filtering_performance_benchmarks", _DEV_UP, "mandatory"),
    _attestation("c004_1_out_of_scope_guardrails", _DEV_UP, "mandatory"),
    _attestation("c004_2_out_of_scope_attempt_logs", _DEV_UP, "mandatory"),
    _attestation("c004_3_user_guidance_on_scope", _DEV_UP, "mandatory"),
    _attestation("c005_1_risk_detection_response", _DEV_UP, "mandatory"),
    _attestation("c005_2_human_review_workflows", _DEV_UP, "mandatory"),
    _attestation("c005_3_automated_response_mechanisms", _DEV_UP, "mandatory"),
    _attestation("c006_1_output_sanitization", _DEV_UP, "mandatory"),
    _attestation("c006_2_warning_labels_untrusted_content", _DEV_UP, "mandatory"),
    _attestation("c006_3_adversarial_output_detection", _DEV_UP, "mandatory"),
    _attestation("c007_1_high_risk_criteria_definition", _DEV_UP, "mandatory"),
    _attestation("c007_2_high_risk_detection_mechanisms", _DEV_UP, "mandatory"),
    _attestation("c007_3_human_review_for_high_risk", _DEV_UP, "mandatory"),
    _attestation("c008_1_risk_monitoring_logs", _DEV_UP, "mandatory"),
    _attestation("c008_2_monitoring_findings_documentation", _DEV_UP, "mandatory"),
    _attestation("c008_4_security_tooling_integration", _DEV_UP, "mandatory"),
    _attestation("c009_1_user_intervention_mechanisms", _DEV_UP, "mandatory"),
    _attestation("c009_2_feedback_intervention_reviews", _DEV_UP, "mandatory"),
    _attestation("c010_1_harmful_output_testing_report", _DEV_UP, "mandatory"),
    _attestation("c011_1_outofscope_output_testing_report", _DEV_UP, "mandatory"),
    _attestation("c012_1_customer_risk_testing_report", _DEV_UP, "mandatory"),
]

_AIUC1_DATA_PRIVACY = [
    _attestation("a001_1_policy_documentation", _SANDBOX_UP, "recommended"),
    _attestation("a001_2_data_retention_implementation", _SANDBOX_UP, "recommended"),
    _attestation("a001_3_data_subject_right_processes", _SANDBOX_UP, "recommended"),
    _attestation("a002_1_output_usage_ownership_policy", _SANDBOX_UP, "recommended"),
    _attestation("a003_1_data_collection_scoping", _SANDBOX_UP, "recommended"),
    _attestation("a003_2_alerting_for_auth_failures", _SANDBOX_UP, "recommended"),
    _attestation("a003_3_authorization_system_integration", _SANDBOX_UP, "recommended"),
    _attestation("a004_1_user_guidance_on_confidential_info", _SANDBOX_UP, "recommended"),
    _attestation("a004_2_foundational_model_ip_protections", _SANDBOX_UP, "recommended"),
    _attestation("a006_1_pii_detection_filtering", _DEV_UP, "mandatory"),
    _attestation("a006_2_pii_access_controls", _DEV_UP, "mandatory"),
    _attestation("a006_3_dlp_system_integration", _DEV_UP, "mandatory"),
]

_AIUC1_ACCOUNTABILITY = [
    _attestation("e001_1_security_breach_failure_plan", _DEV_UP, "mandatory"),
    _attestation("e002_1_harmful_output_failure_plan", _DEV_UP, "mandatory"),
    _attestation("e004_1_change_approval_policy_records", _DEV_UP, "mandatory"),
    _attestation("e005_1_deployment_decisions", _DEV_UP, "mandatory"),
    _attestation("e010_1_acceptable_use_policy", _DEV_UP, "mandatory"),
    _attestation("e015_1_logging_implementation", _DEV_UP, "mandatory"),
    _attestation("e016_1_text_ai_disclosure", _DEV_UP, "mandatory"),
    _attestation("e017_1_transparency_policy", _DEV_UP, "mandatory"),
    _attestation("e017_2_model_cards_system_documentation", _DEV_UP, "mandatory"),
    _attestation("e012_1_regulatory_compliance_reviews", _PREPROD_UP, "mandatory"),
]

_AIUC1_RELIABILITY = [
    _attestation("d001_1_groundedness_filter", _DEV_UP, "recommended"),
    _attestation("d001_2_user_citations_source_attribution", _DEV_UP, "recommended"),
    _attestation("d002_1_hallucination_testing_report", _DEV_UP, "recommended"),
    _attestation("d003_1_tool_authorization_validation", _DEV_UP, "mandatory"),
    _attestation("d003_2_rate_limits_for_tools", _DEV_UP, "mandatory"),
    _attestation("d004_1_tool_call_testing_report", _DEV_UP, "recommended"),
]

# OWASP LLM Top 10
_OWASP_LLM = [
    _scan("llm01_prompt_injection", _DEV_UP, "mandatory"),
    _scan("llm02_insecure_output_handling", _DEV_UP, "mandatory"),
    _attestation("llm03_training_data_poisoning", _DEV_UP, "mandatory"),
    _derived("llm04_model_denial_of_service", _DEV_UP, "mandatory"),
    _artifact("llm05_supply_chain_vulnerabilities", _DEV_UP, "mandatory"),
    _scan("llm06_sensitive_info_disclosure", _DEV_UP, "mandatory"),
    _scan("llm07_insecure_plugin_design", _DEV_UP, "mandatory"),
    _attestation("llm08_excessive_agency", _DEV_UP, "mandatory"),
    _attestation("llm09_overreliance", _DEV_UP, "recommended"),
    _derived("llm10_model_theft", _PREPROD_UP, "mandatory"),
]

# OWASP Web Top 10
_OWASP_WEB = [
    _scan("a01_broken_access_control", _DEV_UP, "mandatory"),
    _scan("a02_cryptographic_failures", _DEV_UP, "mandatory"),
    _scan("a03_injection", _DEV_UP, "mandatory"),
    _derived("a04_insecure_design", _DEV_UP, "recommended"),
    _scan("a05_security_misconfiguration", _DEV_UP, "mandatory"),
    _scan("a06_vulnerable_components", _DEV_UP, "mandatory"),
    _scan("a07_auth_failures", _DEV_UP, "mandatory"),
    _artifact("a08_software_integrity_failures", _DEV_UP, "mandatory"),
    _derived("a09_logging_monitoring_failures", _DEV_UP, "recommended"),
    _scan("a10_ssrf", _DEV_UP, "mandatory"),
]

# MITRE ATLAS
_MITRE_ATLAS = [
    _attestation("aml_t0000_phishing_for_ml_info", _DEV_UP, "recommended"),
    _derived("aml_t0001_discover_ml_artifacts", _DEV_UP, "recommended"),
    _attestation("aml_t0016_obtain_capabilities", _DEV_UP, "recommended"),
    _artifact("aml_t0051_supply_chain_compromise", _DEV_UP, "mandatory"),
    _scan("aml_t0012_valid_accounts", _DEV_UP, "mandatory"),
    _derived("aml_t0040_inference_api_access", _DEV_UP, "recommended"),
    _attestation("aml_t0043_craft_adversarial_data", _DEV_UP, "mandatory"),
    _scan("aml_t0057_llm_prompt_injection", _DEV_UP, "mandatory"),
    _derived("aml_t0024_exfiltration_via_ml_inference", _DEV_UP, "recommended"),
    _derived("aml_t0029_denial_of_ml_service", _DEV_UP, "recommended"),
    _attestation("aml_t0031_erode_model_integrity", _PREPROD_UP, "mandatory"),
]

# SLSA
_SLSA = [
    _artifact("level_1", _SANDBOX_UP, "recommended"),
    _artifact("level_2", _DEV_UP, "mandatory"),
    _artifact("level_3", _PREPROD_UP, "mandatory"),
    _artifact("sbom_generated", _DEV_UP, "mandatory"),
    _artifact("artifact_signed", _DEV_UP, "mandatory"),
    _scan("dependency_review", _DEV_UP, "mandatory"),
    _scan("no_critical_cves", _DEV_UP, "mandatory"),
    _derived("license_cleared", _DEV_UP, "recommended"),
]

# NIST AI RMF
_NIST_RMF = [
    _attestation("policy_defined", _DEV_UP, "mandatory"),
    _attestation("roles_defined", _DEV_UP, "mandatory"),
    _derived("oversight_mechanism", _DEV_UP, "mandatory"),
    _attestation("risk_categorized", _DEV_UP, "mandatory"),
    _derived("threat_assessment", _DEV_UP, "mandatory"),
    _attestation("context_established", _SANDBOX_UP, "recommended"),
    _attestation("metrics_defined", _DEV_UP, "recommended"),
    _derived("monitoring_plan", _DEV_UP, "recommended"),
    _artifact("bias_evaluated", _DEV_UP, "mandatory"),
    _attestation("incident_plan", _DEV_UP, "mandatory"),
    _derived("risk_treatment", _DEV_UP, "mandatory"),
    _attestation("rollback_plan", _DEV_UP, "mandatory"),
]

# NIST SSDF
_NIST_SSDF = [
    _attestation("po1_security_requirements", _SANDBOX_UP, "recommended"),
    _attestation("po2_roles_responsibilities", _SANDBOX_UP, "recommended"),
    _derived("po3_third_party_management", _DEV_UP, "mandatory"),
    _attestation("pw1_security_design", _DEV_UP, "mandatory"),
    _artifact("pw2_threat_modeling", _DEV_UP, "recommended"),
    _derived("pw4_reusable_components", _DEV_UP, "recommended"),
    _derived("pw5_secure_defaults", _DEV_UP, "mandatory"),
    _derived("pw6_code_review", _DEV_UP, "mandatory"),
    _scan("pw7_security_testing", _DEV_UP, "mandatory"),
    _scan("pw8_vulnerability_scanning", _DEV_UP, "mandatory"),
    _attestation("rv1_disclosure_process", _DEV_UP, "mandatory"),
    _derived("rv2_root_cause_analysis", _DEV_UP, "recommended"),
    _derived("rv3_remediation", _DEV_UP, "mandatory"),
]


FRAMEWORK_CATALOGUE: dict[str, list[dict]] = {
    "aiuc1": _AIUC1_DATA_PRIVACY + _AIUC1_SECURITY + _AIUC1_SAFETY + _AIUC1_ACCOUNTABILITY + _AIUC1_RELIABILITY,
    "owasp_llm": _OWASP_LLM,
    "owasp_web": _OWASP_WEB,
    "mitre_atlas": _MITRE_ATLAS,
    "slsa": _SLSA,
    "nist_rmf": _NIST_RMF,
    "ssdf": _NIST_SSDF,
}
