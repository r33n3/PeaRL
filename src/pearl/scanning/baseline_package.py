"""Tiered governance baseline packages for PeaRL projects.

Structured around the AIUC-1 standard (https://www.aiuc-1.com/) v1.0 (Q1 2026).

Six domains:
  A. Data & Privacy  (a001–a007)
  B. Security        (b001–b009)
  C. Safety          (c001–c012)
  D. Reliability     (d001–d004)
  E. Accountability  (e001–e017, note: e007 merged→e004, e014 merged→e017)
  F. Society         (f001–f002)

Each domain is broken into sub-controls (e.g. a001_1, a001_2) where:
  - _1/_2/... Core sub-controls are required at the tier that mandates the parent
  - Supplemental sub-controls are added at AI-Comprehensive tier

Three tiers:
  - Essential:        All projects regardless of AI usage
  - AI-Standard:      AI-enabled projects (low/moderate criticality)
  - AI-Comprehensive: High-risk AI projects (high/critical criticality)

Field values:
  True   = control is required and must be satisfied before promotion
  False  = control is known but not required at this tier
  null   = not yet assessed
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Essential — every project, regardless of AI usage
# ---------------------------------------------------------------------------

ESSENTIAL_BASELINE: dict[str, Any] = {
    "schema_version": "1.1",
    "kind": "PearlOrgBaseline",
    "baseline_id": "orgb_essential_v1",
    "org_name": "PeaRL Recommended Baseline \u2014 Essential",
    "tier": "essential",
    "defaults": {
        # ── A. Data & Privacy ──────────────────────────────────────────────
        "data_privacy": {
            # A001: Establish input data policy
            "a001_1_policy_documentation": True,
            "a001_2_data_retention_implementation": True,
            "a001_3_data_subject_right_processes": False,      # Supplemental
            # A002: Establish output data policy
            "a002_1_output_usage_ownership_policy": True,
            # A003: Limit AI agent data collection (AI-specific)
            "a003_1_data_collection_scoping": False,
            "a003_2_alerting_for_auth_failures": False,        # Supplemental
            "a003_3_authorization_system_integration": False,  # Supplemental
            # A004: Protect IP & trade secrets
            "a004_1_user_guidance_on_confidential_info": True,
            "a004_2_foundational_model_ip_protections": False, # Supplemental
            "a004_3_ip_detection_implementation": False,       # Supplemental
            "a004_4_ip_disclosure_monitoring": False,          # Supplemental
            # A005: Prevent cross-customer data exposure
            "a005_1_consent_for_combined_data": True,
            "a005_2_customer_data_isolation": True,
            "a005_3_privacy_enhancing_controls": False,        # Supplemental
            # A006: Prevent PII leakage
            "a006_1_pii_detection_filtering": True,
            "a006_2_pii_access_controls": True,
            "a006_3_dlp_system_integration": False,            # Supplemental
            # A007: Prevent IP violations (External-facing — not required at Essential)
            "a007_1_model_provider_ip_protections": False,
            "a007_2_ip_infringement_filtering": False,         # Supplemental
            "a007_3_user_facing_ip_notices": False,            # Supplemental
        },
        # ── B. Security ────────────────────────────────────────────────────
        "security": {
            # B001: Third-party adversarial robustness testing (AI-specific)
            "b001_1_adversarial_testing_report": False,
            "b001_2_security_program_integration": False,      # Supplemental
            # B002: Detect adversarial input (Optional)
            "b002_1_adversarial_input_detection_alerting": False,
            "b002_2_adversarial_incident_response": False,
            "b002_3_detection_config_updates": False,
            "b002_4_preprocessing_adversarial_detection": False,  # Supplemental
            "b002_5_ai_security_alerts": False,                # Supplemental
            # B003: Manage public release of technical details (Optional)
            "b003_1_technical_disclosure_guidelines": False,
            "b003_2_public_disclosure_approval_records": False,  # Supplemental
            # B004: Prevent AI endpoint scraping (Mandatory)
            "b004_1_anomalous_usage_detection": True,
            "b004_2_rate_limits": True,
            "b004_3_external_pentest_ai_endpoints": False,     # Required for AI
            "b004_4_vulnerability_remediation": True,
            # B005: Real-time input filtering (Optional)
            "b005_1_input_filtering": False,
            "b005_2_input_moderation_approach": False,
            "b005_3_warning_for_blocked_inputs": False,        # Supplemental
            "b005_4_input_filtering_logs": False,              # Supplemental
            "b005_5_input_filter_performance": False,          # Supplemental
            # B006: Prevent unauthorized AI agent actions (AI-specific)
            "b006_1_agent_service_access_restrictions": False,
            "b006_2_agent_security_monitoring_alerting": False,
            # B007: Enforce user access privileges (Mandatory)
            "b007_1_user_access_controls": True,
            "b007_2_access_reviews": True,
            # B008: Protect model deployment environment (Mandatory)
            "b008_1_model_access_controls": True,
            "b008_2_api_deployment_security": True,
            "b008_3_model_hosting_security": False,            # Supplemental
            "b008_4_model_integrity_verification": False,      # Supplemental
            # B009: Limit output over-exposure (AI-specific)
            "b009_1_output_volume_limits": False,
            "b009_2_user_output_notices": False,
            "b009_3_output_precision_controls": False,
        },
        # ── C. Safety ──────────────────────────────────────────────────────
        "safety": {
            # C001: Define AI risk taxonomy (Mandatory)
            "c001_1_risk_taxonomy": True,
            "c001_2_risk_taxonomy_reviews": True,
            # C002: Conduct pre-deployment testing (Mandatory)
            "c002_1_pre_deployment_test_approval": True,
            "c002_2_sdlc_integration": True,
            "c002_3_vulnerability_scan_results": True,
            # C003: Prevent harmful outputs (AI-specific)
            "c003_1_harmful_output_filtering": False,
            "c003_2_guardrails_for_high_risk_advice": False,
            "c003_3_guardrails_for_biased_outputs": False,     # Supplemental
            "c003_4_filtering_performance_benchmarks": False,  # Supplemental
            # C004: Prevent out-of-scope outputs (AI-specific)
            "c004_1_out_of_scope_guardrails": False,
            "c004_2_out_of_scope_attempt_logs": False,
            "c004_3_user_guidance_on_scope": False,            # Supplemental
            # C005: Prevent customer-defined high risk outputs (AI-specific)
            "c005_1_risk_detection_response": False,
            "c005_2_human_review_workflows": False,
            "c005_3_automated_response_mechanisms": False,
            # C006: Prevent output vulnerabilities (AI-specific)
            "c006_1_output_sanitization": False,
            "c006_2_warning_labels_untrusted_content": False,
            "c006_3_adversarial_output_detection": False,      # Supplemental
            # C007: Flag high risk outputs (Optional)
            "c007_1_high_risk_criteria_definition": False,
            "c007_2_high_risk_detection_mechanisms": False,
            "c007_3_human_review_for_high_risk": False,        # Supplemental
            # C008: Monitor AI risk categories (Optional)
            "c008_1_risk_monitoring_logs": False,
            "c008_2_monitoring_findings_documentation": False,
            "c008_4_security_tooling_integration": False,      # Supplemental
            # C009: Real-time feedback and intervention (Optional)
            "c009_1_user_intervention_mechanisms": False,
            "c009_2_feedback_intervention_reviews": False,
            # C010/C011/C012: Third-party testing (AI-specific)
            "c010_1_harmful_output_testing_report": False,
            "c011_1_outofscope_output_testing_report": False,
            "c012_1_customer_risk_testing_report": False,
        },
        # ── D. Reliability ─────────────────────────────────────────────────
        "reliability": {
            # All reliability controls are AI-specific
            "d001_1_groundedness_filter": False,
            "d001_2_user_citations_source_attribution": False,
            "d001_3_user_uncertainty_labels": False,           # Supplemental
            "d002_1_hallucination_testing_report": False,
            "d003_1_tool_authorization_validation": False,
            "d003_2_rate_limits_for_tools": False,
            "d003_3_tool_call_log": False,
            "d003_4_human_approval_workflows": False,          # Supplemental
            "d003_5_tool_call_log_reviews": False,             # Supplemental
            "d004_1_tool_call_testing_report": False,
        },
        # ── E. Accountability ──────────────────────────────────────────────
        "accountability": {
            # E001: AI failure plan for security breaches (Mandatory)
            "e001_1_security_breach_failure_plan": True,
            # E002: AI failure plan for harmful outputs (AI-specific)
            "e002_1_harmful_output_failure_plan": False,
            "e002_2_harmful_output_failure_procedures": False, # Supplemental
            # E003: AI failure plan for hallucinations (AI-specific)
            "e003_1_hallucination_failure_plan": False,
            "e003_2_hallucination_failure_procedures": False,
            # E004: Assign accountability (Mandatory; E007 merged here Q1 2026)
            "e004_1_change_approval_policy_records": True,
            "e004_2_code_signing_implementation": True,
            # E005: Assess cloud vs on-prem (Mandatory)
            "e005_1_deployment_decisions": True,
            # E006: Vendor due diligence (Mandatory)
            "e006_1_vendor_due_diligence": True,
            # E008: Review internal processes (Mandatory)
            "e008_1_internal_review_documentation": True,
            "e008_2_external_feedback_integration": False,     # Supplemental
            # E009: Monitor third-party access (Optional)
            "e009_1_third_party_access_monitoring": False,
            # E010: AI acceptable use policy (Mandatory)
            "e010_1_acceptable_use_policy": True,
            "e010_2_aup_violation_detection": True,
            "e010_3_user_notification_for_aup_breaches": True,
            "e010_4_guardrails_enforcing_acceptable_use": False,  # Supplemental
            # E011: Record processing locations (Mandatory)
            "e011_1_ai_processing_locations": True,
            "e011_2_data_transfer_compliance": True,
            # E012: Regulatory compliance documentation (Mandatory)
            "e012_1_regulatory_compliance_reviews": True,
            # E013: Quality management system (Optional)
            "e013_1_quality_objectives_risk_management": False,
            "e013_2_change_management_procedures": False,
            "e013_3_issue_tracking_monitoring": False,
            "e013_4_data_management_procedures": False,        # Supplemental
            "e013_5_stakeholder_communication_procedures": False,  # Supplemental
            # E015: Log model activity (AI-specific)
            "e015_1_logging_implementation": False,
            "e015_2_log_storage": False,
            "e015_3_log_integrity_protection": False,          # Supplemental
            # E016: AI disclosure mechanisms (AI-specific)
            "e016_1_text_ai_disclosure": False,
            "e016_2_voice_ai_disclosure": False,
            "e016_3_labelling_ai_generated_content": False,
            "e016_4_automation_ai_disclosure": False,
            "e016_5_system_response_to_ai_inquiry": False,
            # E017: Transparency policy (Optional; E014 merged here Q1 2026)
            "e017_1_transparency_policy": False,
            "e017_2_model_cards_system_documentation": False,
            "e017_3_transparency_report_sharing_policy": False,  # Supplemental
        },
        # ── F. Society ─────────────────────────────────────────────────────
        "society": {
            # F001: Prevent AI cyber misuse (Mandatory)
            "f001_1_foundation_model_cyber_capabilities": True,
            "f001_2_cyber_use_detection": False,               # Supplemental
            # F002: Prevent catastrophic misuse — CBRN (Mandatory)
            "f002_1_foundation_model_cbrn_capabilities": True,
            "f002_2_catastrophic_misuse_monitoring": False,    # Supplemental
        },
    },
}


# ---------------------------------------------------------------------------
# AI-Standard — AI-enabled projects at low / moderate business criticality
# Upgrades all AI-specific mandatory Core sub-controls to True.
# ---------------------------------------------------------------------------

AI_STANDARD_BASELINE: dict[str, Any] = {
    "schema_version": "1.1",
    "kind": "PearlOrgBaseline",
    "baseline_id": "orgb_ai_standard_v1",
    "org_name": "PeaRL Recommended Baseline \u2014 AI-Standard",
    "tier": "ai_standard",
    "defaults": {
        # ── A. Data & Privacy ──────────────────────────────────────────────
        "data_privacy": {
            "a001_1_policy_documentation": True,
            "a001_2_data_retention_implementation": True,
            "a001_3_data_subject_right_processes": False,
            "a002_1_output_usage_ownership_policy": True,
            # A003: Upgraded — AI agents require data scoping
            "a003_1_data_collection_scoping": True,
            "a003_2_alerting_for_auth_failures": False,
            "a003_3_authorization_system_integration": False,
            "a004_1_user_guidance_on_confidential_info": True,
            # A004.2: Important for AI — know what your model provider protects
            "a004_2_foundational_model_ip_protections": True,
            "a004_3_ip_detection_implementation": False,
            "a004_4_ip_disclosure_monitoring": False,
            "a005_1_consent_for_combined_data": True,
            "a005_2_customer_data_isolation": True,
            "a005_3_privacy_enhancing_controls": False,
            "a006_1_pii_detection_filtering": True,
            "a006_2_pii_access_controls": True,
            "a006_3_dlp_system_integration": False,
            # A007: Upgraded — AI outputs create IP violation risk
            "a007_1_model_provider_ip_protections": True,
            "a007_2_ip_infringement_filtering": False,
            "a007_3_user_facing_ip_notices": False,
        },
        # ── B. Security ────────────────────────────────────────────────────
        "security": {
            # B001: Upgraded — Mandatory for AI systems
            "b001_1_adversarial_testing_report": True,
            "b001_2_security_program_integration": False,
            # B002: Still optional but recommended
            "b002_1_adversarial_input_detection_alerting": False,
            "b002_2_adversarial_incident_response": False,
            "b002_3_detection_config_updates": False,
            "b002_4_preprocessing_adversarial_detection": False,
            "b002_5_ai_security_alerts": False,
            "b003_1_technical_disclosure_guidelines": False,
            "b003_2_public_disclosure_approval_records": False,
            "b004_1_anomalous_usage_detection": True,
            "b004_2_rate_limits": True,
            # B004.3: Upgraded — pentesting required for AI endpoints
            "b004_3_external_pentest_ai_endpoints": True,
            "b004_4_vulnerability_remediation": True,
            "b005_1_input_filtering": False,
            "b005_2_input_moderation_approach": False,
            "b005_3_warning_for_blocked_inputs": False,
            "b005_4_input_filtering_logs": False,
            "b005_5_input_filter_performance": False,
            # B006: Upgraded — required for AI agent deployments
            "b006_1_agent_service_access_restrictions": True,
            "b006_2_agent_security_monitoring_alerting": True,
            "b007_1_user_access_controls": True,
            "b007_2_access_reviews": True,
            "b008_1_model_access_controls": True,
            "b008_2_api_deployment_security": True,
            "b008_3_model_hosting_security": False,
            "b008_4_model_integrity_verification": False,
            # B009: Upgraded — required for AI output systems
            "b009_1_output_volume_limits": True,
            "b009_2_user_output_notices": True,
            "b009_3_output_precision_controls": False,
        },
        # ── C. Safety ──────────────────────────────────────────────────────
        "safety": {
            "c001_1_risk_taxonomy": True,
            "c001_2_risk_taxonomy_reviews": True,
            "c002_1_pre_deployment_test_approval": True,
            "c002_2_sdlc_integration": True,
            "c002_3_vulnerability_scan_results": True,
            # C003: Upgraded — harmful output safeguards required for AI
            "c003_1_harmful_output_filtering": True,
            "c003_2_guardrails_for_high_risk_advice": True,
            "c003_3_guardrails_for_biased_outputs": False,
            "c003_4_filtering_performance_benchmarks": False,
            # C004: Upgraded — out-of-scope guardrails required for AI
            "c004_1_out_of_scope_guardrails": True,
            "c004_2_out_of_scope_attempt_logs": True,
            "c004_3_user_guidance_on_scope": False,
            # C005: Upgraded — customer risk controls required for AI
            "c005_1_risk_detection_response": True,
            "c005_2_human_review_workflows": True,
            "c005_3_automated_response_mechanisms": True,
            # C006: Upgraded — output vulnerability prevention required for AI
            "c006_1_output_sanitization": True,
            "c006_2_warning_labels_untrusted_content": True,
            "c006_3_adversarial_output_detection": False,
            # C007/C008/C009: Optional at this tier
            "c007_1_high_risk_criteria_definition": False,
            "c007_2_high_risk_detection_mechanisms": False,
            "c007_3_human_review_for_high_risk": False,
            "c008_1_risk_monitoring_logs": False,
            "c008_2_monitoring_findings_documentation": False,
            "c008_4_security_tooling_integration": False,
            "c009_1_user_intervention_mechanisms": False,
            "c009_2_feedback_intervention_reviews": False,
            # C010/C011/C012: Upgraded — third-party testing required for AI
            "c010_1_harmful_output_testing_report": True,
            "c011_1_outofscope_output_testing_report": True,
            "c012_1_customer_risk_testing_report": True,
        },
        # ── D. Reliability ─────────────────────────────────────────────────
        "reliability": {
            # All core reliability controls required for AI-Standard
            "d001_1_groundedness_filter": True,
            "d001_2_user_citations_source_attribution": True,
            "d001_3_user_uncertainty_labels": False,
            "d002_1_hallucination_testing_report": True,
            "d003_1_tool_authorization_validation": True,
            "d003_2_rate_limits_for_tools": True,
            "d003_3_tool_call_log": True,
            "d003_4_human_approval_workflows": False,
            "d003_5_tool_call_log_reviews": False,
            "d004_1_tool_call_testing_report": True,
        },
        # ── E. Accountability ──────────────────────────────────────────────
        "accountability": {
            "e001_1_security_breach_failure_plan": True,
            # E002/E003: Upgraded — AI failure plans required
            "e002_1_harmful_output_failure_plan": True,
            "e002_2_harmful_output_failure_procedures": False,
            "e003_1_hallucination_failure_plan": True,
            "e003_2_hallucination_failure_procedures": True,
            "e004_1_change_approval_policy_records": True,
            "e004_2_code_signing_implementation": True,
            "e005_1_deployment_decisions": True,
            "e006_1_vendor_due_diligence": True,
            "e008_1_internal_review_documentation": True,
            "e008_2_external_feedback_integration": False,
            "e009_1_third_party_access_monitoring": False,
            "e010_1_acceptable_use_policy": True,
            "e010_2_aup_violation_detection": True,
            "e010_3_user_notification_for_aup_breaches": True,
            "e010_4_guardrails_enforcing_acceptable_use": False,
            "e011_1_ai_processing_locations": True,
            "e011_2_data_transfer_compliance": True,
            "e012_1_regulatory_compliance_reviews": True,
            "e013_1_quality_objectives_risk_management": False,
            "e013_2_change_management_procedures": False,
            "e013_3_issue_tracking_monitoring": False,
            "e013_4_data_management_procedures": False,
            "e013_5_stakeholder_communication_procedures": False,
            # E015/E016: Upgraded — model logging + disclosure required for AI
            "e015_1_logging_implementation": True,
            "e015_2_log_storage": True,
            "e015_3_log_integrity_protection": False,
            "e016_1_text_ai_disclosure": True,
            "e016_2_voice_ai_disclosure": True,
            "e016_3_labelling_ai_generated_content": True,
            "e016_4_automation_ai_disclosure": True,
            "e016_5_system_response_to_ai_inquiry": True,
            "e017_1_transparency_policy": False,
            "e017_2_model_cards_system_documentation": False,
            "e017_3_transparency_report_sharing_policy": False,
        },
        # ── F. Society ─────────────────────────────────────────────────────
        "society": {
            "f001_1_foundation_model_cyber_capabilities": True,
            # F001.2: Upgraded — AI systems need active cyber use detection
            "f001_2_cyber_use_detection": True,
            "f002_1_foundation_model_cbrn_capabilities": True,
            "f002_2_catastrophic_misuse_monitoring": False,
        },
    },
}


# ---------------------------------------------------------------------------
# AI-Comprehensive — high-risk AI projects (high / critical criticality)
# All Core + Supplemental sub-controls required.
# ---------------------------------------------------------------------------

AI_COMPREHENSIVE_BASELINE: dict[str, Any] = {
    "schema_version": "1.1",
    "kind": "PearlOrgBaseline",
    "baseline_id": "orgb_ai_comprehensive_v1",
    "org_name": "PeaRL Recommended Baseline \u2014 AI-Comprehensive",
    "tier": "ai_comprehensive",
    "defaults": {
        # ── A. Data & Privacy ──────────────────────────────────────────────
        "data_privacy": {
            "a001_1_policy_documentation": True,
            "a001_2_data_retention_implementation": True,
            "a001_3_data_subject_right_processes": True,       # Supplemental → required
            "a002_1_output_usage_ownership_policy": True,
            "a003_1_data_collection_scoping": True,
            "a003_2_alerting_for_auth_failures": True,         # Supplemental → required
            "a003_3_authorization_system_integration": True,   # Supplemental → required
            "a004_1_user_guidance_on_confidential_info": True,
            "a004_2_foundational_model_ip_protections": True,
            "a004_3_ip_detection_implementation": True,        # Supplemental → required
            "a004_4_ip_disclosure_monitoring": True,           # Supplemental → required
            "a005_1_consent_for_combined_data": True,
            "a005_2_customer_data_isolation": True,
            "a005_3_privacy_enhancing_controls": True,         # Supplemental → required
            "a006_1_pii_detection_filtering": True,
            "a006_2_pii_access_controls": True,
            "a006_3_dlp_system_integration": True,             # Supplemental → required
            "a007_1_model_provider_ip_protections": True,
            "a007_2_ip_infringement_filtering": True,          # Supplemental → required
            "a007_3_user_facing_ip_notices": True,             # Supplemental → required
        },
        # ── B. Security ────────────────────────────────────────────────────
        "security": {
            "b001_1_adversarial_testing_report": True,
            "b001_2_security_program_integration": True,       # Supplemental → required
            # B002: Upgraded — adversarial detection required for high-risk AI
            "b002_1_adversarial_input_detection_alerting": True,
            "b002_2_adversarial_incident_response": True,
            "b002_3_detection_config_updates": True,
            "b002_4_preprocessing_adversarial_detection": True,  # Supplemental → required
            "b002_5_ai_security_alerts": True,                 # Supplemental → required
            # B003: Upgraded — public release management required for high-risk AI
            "b003_1_technical_disclosure_guidelines": True,
            "b003_2_public_disclosure_approval_records": True, # Supplemental → required
            "b004_1_anomalous_usage_detection": True,
            "b004_2_rate_limits": True,
            "b004_3_external_pentest_ai_endpoints": True,
            "b004_4_vulnerability_remediation": True,
            # B005: Upgraded — real-time filtering required for high-risk AI
            "b005_1_input_filtering": True,
            "b005_2_input_moderation_approach": True,
            "b005_3_warning_for_blocked_inputs": True,         # Supplemental → required
            "b005_4_input_filtering_logs": True,               # Supplemental → required
            "b005_5_input_filter_performance": True,           # Supplemental → required
            "b006_1_agent_service_access_restrictions": True,
            "b006_2_agent_security_monitoring_alerting": True,
            "b007_1_user_access_controls": True,
            "b007_2_access_reviews": True,
            "b008_1_model_access_controls": True,
            "b008_2_api_deployment_security": True,
            "b008_3_model_hosting_security": True,             # Supplemental → required
            "b008_4_model_integrity_verification": True,       # Supplemental → required
            "b009_1_output_volume_limits": True,
            "b009_2_user_output_notices": True,
            "b009_3_output_precision_controls": True,          # Upgraded for high-risk
        },
        # ── C. Safety ──────────────────────────────────────────────────────
        "safety": {
            "c001_1_risk_taxonomy": True,
            "c001_2_risk_taxonomy_reviews": True,
            "c002_1_pre_deployment_test_approval": True,
            "c002_2_sdlc_integration": True,
            "c002_3_vulnerability_scan_results": True,
            "c003_1_harmful_output_filtering": True,
            "c003_2_guardrails_for_high_risk_advice": True,
            "c003_3_guardrails_for_biased_outputs": True,      # Supplemental → required
            "c003_4_filtering_performance_benchmarks": True,   # Supplemental → required
            "c004_1_out_of_scope_guardrails": True,
            "c004_2_out_of_scope_attempt_logs": True,
            "c004_3_user_guidance_on_scope": True,             # Supplemental → required
            "c005_1_risk_detection_response": True,
            "c005_2_human_review_workflows": True,
            "c005_3_automated_response_mechanisms": True,
            "c006_1_output_sanitization": True,
            "c006_2_warning_labels_untrusted_content": True,
            "c006_3_adversarial_output_detection": True,       # Supplemental → required
            # C007: Upgraded — high-risk output flagging required
            "c007_1_high_risk_criteria_definition": True,
            "c007_2_high_risk_detection_mechanisms": True,
            "c007_3_human_review_for_high_risk": True,         # Supplemental → required
            # C008: Upgraded — continuous AI risk monitoring required
            "c008_1_risk_monitoring_logs": True,
            "c008_2_monitoring_findings_documentation": True,
            "c008_4_security_tooling_integration": True,       # Supplemental → required
            # C009: Upgraded — real-time intervention required for high-risk AI
            "c009_1_user_intervention_mechanisms": True,
            "c009_2_feedback_intervention_reviews": True,
            "c010_1_harmful_output_testing_report": True,
            "c011_1_outofscope_output_testing_report": True,
            "c012_1_customer_risk_testing_report": True,
        },
        # ── D. Reliability ─────────────────────────────────────────────────
        "reliability": {
            "d001_1_groundedness_filter": True,
            "d001_2_user_citations_source_attribution": True,
            "d001_3_user_uncertainty_labels": True,            # Supplemental → required
            "d002_1_hallucination_testing_report": True,
            "d003_1_tool_authorization_validation": True,
            "d003_2_rate_limits_for_tools": True,
            "d003_3_tool_call_log": True,
            "d003_4_human_approval_workflows": True,           # Supplemental → required
            "d003_5_tool_call_log_reviews": True,              # Supplemental → required
            "d004_1_tool_call_testing_report": True,
        },
        # ── E. Accountability ──────────────────────────────────────────────
        "accountability": {
            "e001_1_security_breach_failure_plan": True,
            "e002_1_harmful_output_failure_plan": True,
            "e002_2_harmful_output_failure_procedures": True,  # Supplemental → required
            "e003_1_hallucination_failure_plan": True,
            "e003_2_hallucination_failure_procedures": True,
            "e004_1_change_approval_policy_records": True,
            "e004_2_code_signing_implementation": True,
            "e005_1_deployment_decisions": True,
            "e006_1_vendor_due_diligence": True,
            "e008_1_internal_review_documentation": True,
            "e008_2_external_feedback_integration": True,      # Supplemental → required
            "e009_1_third_party_access_monitoring": True,      # Upgraded — required
            "e010_1_acceptable_use_policy": True,
            "e010_2_aup_violation_detection": True,
            "e010_3_user_notification_for_aup_breaches": True,
            "e010_4_guardrails_enforcing_acceptable_use": True,  # Supplemental → required
            "e011_1_ai_processing_locations": True,
            "e011_2_data_transfer_compliance": True,
            "e012_1_regulatory_compliance_reviews": True,
            # E013: Upgraded — quality management required for high-risk AI
            "e013_1_quality_objectives_risk_management": True,
            "e013_2_change_management_procedures": True,
            "e013_3_issue_tracking_monitoring": True,
            "e013_4_data_management_procedures": True,         # Supplemental → required
            "e013_5_stakeholder_communication_procedures": True,  # Supplemental → required
            "e015_1_logging_implementation": True,
            "e015_2_log_storage": True,
            "e015_3_log_integrity_protection": True,           # Supplemental → required
            "e016_1_text_ai_disclosure": True,
            "e016_2_voice_ai_disclosure": True,
            "e016_3_labelling_ai_generated_content": True,
            "e016_4_automation_ai_disclosure": True,
            "e016_5_system_response_to_ai_inquiry": True,
            # E017: Upgraded — full transparency required for high-risk AI
            "e017_1_transparency_policy": True,
            "e017_2_model_cards_system_documentation": True,
            "e017_3_transparency_report_sharing_policy": True, # Supplemental → required
        },
        # ── F. Society ─────────────────────────────────────────────────────
        "society": {
            "f001_1_foundation_model_cyber_capabilities": True,
            "f001_2_cyber_use_detection": True,
            "f002_1_foundation_model_cbrn_capabilities": True,
            "f002_2_catastrophic_misuse_monitoring": True,     # Supplemental → required
        },
    },
}


# ---------------------------------------------------------------------------
# AIUC-1 sub-control registry: maps field key → human-readable label
# Used by the UI and gate rule descriptions.
# Format: "{category}.{field_key}" → "XNNx.y: Description"
# ---------------------------------------------------------------------------

AIUC1_CONTROLS: dict[str, str] = {
    # ── A. Data & Privacy ──────────────────────────────────────────────────
    "data_privacy.a001_1_policy_documentation": "A001.1: Input data policy documentation",
    "data_privacy.a001_2_data_retention_implementation": "A001.2: Data retention implementation",
    "data_privacy.a001_3_data_subject_right_processes": "A001.3: Data subject right processes",
    "data_privacy.a002_1_output_usage_ownership_policy": "A002.1: Output usage and ownership policy",
    "data_privacy.a003_1_data_collection_scoping": "A003.1: Data collection scoping",
    "data_privacy.a003_2_alerting_for_auth_failures": "A003.2: Alerting for authorization failures",
    "data_privacy.a003_3_authorization_system_integration": "A003.3: Authorization system integration",
    "data_privacy.a004_1_user_guidance_on_confidential_info": "A004.1: User guidance on confidential information",
    "data_privacy.a004_2_foundational_model_ip_protections": "A004.2: Foundational model IP protections",
    "data_privacy.a004_3_ip_detection_implementation": "A004.3: IP detection implementation",
    "data_privacy.a004_4_ip_disclosure_monitoring": "A004.4: IP disclosure monitoring",
    "data_privacy.a005_1_consent_for_combined_data": "A005.1: Consent for combined data usage",
    "data_privacy.a005_2_customer_data_isolation": "A005.2: Customer data isolation controls",
    "data_privacy.a005_3_privacy_enhancing_controls": "A005.3: Privacy-enhancing controls",
    "data_privacy.a006_1_pii_detection_filtering": "A006.1: PII detection and filtering",
    "data_privacy.a006_2_pii_access_controls": "A006.2: PII access controls",
    "data_privacy.a006_3_dlp_system_integration": "A006.3: DLP system integration",
    "data_privacy.a007_1_model_provider_ip_protections": "A007.1: Model provider IP infringement protections",
    "data_privacy.a007_2_ip_infringement_filtering": "A007.2: IP infringement filtering",
    "data_privacy.a007_3_user_facing_ip_notices": "A007.3: User-facing IP notices",
    # ── B. Security ────────────────────────────────────────────────────────
    "security.b001_1_adversarial_testing_report": "B001.1: Adversarial testing results report",
    "security.b001_2_security_program_integration": "B001.2: Security program integration",
    "security.b002_1_adversarial_input_detection_alerting": "B002.1: Adversarial input detection and alerting",
    "security.b002_2_adversarial_incident_response": "B002.2: Adversarial incident and response logs",
    "security.b002_3_detection_config_updates": "B002.3: Detection configuration updates",
    "security.b002_4_preprocessing_adversarial_detection": "B002.4: Pre-processing adversarial detection",
    "security.b002_5_ai_security_alerts": "B002.5: AI security alerts integration",
    "security.b003_1_technical_disclosure_guidelines": "B003.1: Technical information disclosure guidelines",
    "security.b003_2_public_disclosure_approval_records": "B003.2: Public disclosure approval records",
    "security.b004_1_anomalous_usage_detection": "B004.1: Anomalous usage detection",
    "security.b004_2_rate_limits": "B004.2: Rate limits",
    "security.b004_3_external_pentest_ai_endpoints": "B004.3: External pentest of AI endpoints",
    "security.b004_4_vulnerability_remediation": "B004.4: Vulnerability remediation",
    "security.b005_1_input_filtering": "B005.1: Input filtering implementation",
    "security.b005_2_input_moderation_approach": "B005.2: Input moderation approach documentation",
    "security.b005_3_warning_for_blocked_inputs": "B005.3: Warning for blocked inputs",
    "security.b005_4_input_filtering_logs": "B005.4: Input filtering logs",
    "security.b005_5_input_filter_performance": "B005.5: Input filter performance documentation",
    "security.b006_1_agent_service_access_restrictions": "B006.1: Agent service access restrictions",
    "security.b006_2_agent_security_monitoring_alerting": "B006.2: Agent security monitoring and alerting",
    "security.b007_1_user_access_controls": "B007.1: User access controls",
    "security.b007_2_access_reviews": "B007.2: Access reviews",
    "security.b008_1_model_access_controls": "B008.1: Model access controls",
    "security.b008_2_api_deployment_security": "B008.2: API deployment security",
    "security.b008_3_model_hosting_security": "B008.3: Model hosting security",
    "security.b008_4_model_integrity_verification": "B008.4: Model integrity verification",
    "security.b009_1_output_volume_limits": "B009.1: Output volume limits",
    "security.b009_2_user_output_notices": "B009.2: User output notices",
    "security.b009_3_output_precision_controls": "B009.3: Output precision controls",
    # ── C. Safety ──────────────────────────────────────────────────────────
    "safety.c001_1_risk_taxonomy": "C001.1: AI risk taxonomy documentation",
    "safety.c001_2_risk_taxonomy_reviews": "C001.2: Risk taxonomy reviews",
    "safety.c002_1_pre_deployment_test_approval": "C002.1: Pre-deployment test and approval records",
    "safety.c002_2_sdlc_integration": "C002.2: SDLC integration",
    "safety.c002_3_vulnerability_scan_results": "C002.3: Vulnerability scan results",
    "safety.c003_1_harmful_output_filtering": "C003.1: Harmful output filtering",
    "safety.c003_2_guardrails_for_high_risk_advice": "C003.2: Guardrails for high-risk advice",
    "safety.c003_3_guardrails_for_biased_outputs": "C003.3: Guardrails for biased outputs",
    "safety.c003_4_filtering_performance_benchmarks": "C003.4: Filtering performance benchmarks",
    "safety.c004_1_out_of_scope_guardrails": "C004.1: Out-of-scope output guardrails",
    "safety.c004_2_out_of_scope_attempt_logs": "C004.2: Out-of-scope attempt logs",
    "safety.c004_3_user_guidance_on_scope": "C004.3: User guidance on scope",
    "safety.c005_1_risk_detection_response": "C005.1: Risk detection and response",
    "safety.c005_2_human_review_workflows": "C005.2: Human review workflows",
    "safety.c005_3_automated_response_mechanisms": "C005.3: Automated response mechanisms",
    "safety.c006_1_output_sanitization": "C006.1: Output sanitization",
    "safety.c006_2_warning_labels_untrusted_content": "C006.2: Warning labels for untrusted content",
    "safety.c006_3_adversarial_output_detection": "C006.3: Adversarial output detection",
    "safety.c007_1_high_risk_criteria_definition": "C007.1: High-risk output criteria definition",
    "safety.c007_2_high_risk_detection_mechanisms": "C007.2: High-risk detection mechanisms",
    "safety.c007_3_human_review_for_high_risk": "C007.3: Human review workflows for high-risk outputs",
    "safety.c008_1_risk_monitoring_logs": "C008.1: AI risk monitoring logs",
    "safety.c008_2_monitoring_findings_documentation": "C008.2: Monitoring findings documentation",
    "safety.c008_4_security_tooling_integration": "C008.4: Security tooling integration",
    "safety.c009_1_user_intervention_mechanisms": "C009.1: User intervention mechanisms",
    "safety.c009_2_feedback_intervention_reviews": "C009.2: User feedback and intervention reviews",
    "safety.c010_1_harmful_output_testing_report": "C010.1: Third-party harmful output testing report",
    "safety.c011_1_outofscope_output_testing_report": "C011.1: Third-party out-of-scope output testing report",
    "safety.c012_1_customer_risk_testing_report": "C012.1: Third-party customer-defined risk testing report",
    # ── D. Reliability ─────────────────────────────────────────────────────
    "reliability.d001_1_groundedness_filter": "D001.1: Groundedness filter",
    "reliability.d001_2_user_citations_source_attribution": "D001.2: User-facing citations and source attribution",
    "reliability.d001_3_user_uncertainty_labels": "D001.3: User-facing uncertainty labels",
    "reliability.d002_1_hallucination_testing_report": "D002.1: Third-party hallucination testing report",
    "reliability.d003_1_tool_authorization_validation": "D003.1: Tool authorization and validation",
    "reliability.d003_2_rate_limits_for_tools": "D003.2: Rate limits for tool calls",
    "reliability.d003_3_tool_call_log": "D003.3: Tool call execution log",
    "reliability.d003_4_human_approval_workflows": "D003.4: Human-approval workflows for tool calls",
    "reliability.d003_5_tool_call_log_reviews": "D003.5: Tool call log reviews",
    "reliability.d004_1_tool_call_testing_report": "D004.1: Third-party tool call testing report",
    # ── E. Accountability ──────────────────────────────────────────────────
    "accountability.e001_1_security_breach_failure_plan": "E001.1: AI failure plan for security breaches",
    "accountability.e002_1_harmful_output_failure_plan": "E002.1: AI failure plan for harmful outputs",
    "accountability.e002_2_harmful_output_failure_procedures": "E002.2: Harmful output failure procedures",
    "accountability.e003_1_hallucination_failure_plan": "E003.1: AI failure plan for hallucinations",
    "accountability.e003_2_hallucination_failure_procedures": "E003.2: Hallucination failure procedures",
    "accountability.e004_1_change_approval_policy_records": "E004.1: Change approval policy and records",
    "accountability.e004_2_code_signing_implementation": "E004.2: Code signing implementation",
    "accountability.e005_1_deployment_decisions": "E005.1: Cloud vs on-prem deployment decisions",
    "accountability.e006_1_vendor_due_diligence": "E006.1: Vendor due diligence documentation",
    "accountability.e008_1_internal_review_documentation": "E008.1: Internal process review documentation",
    "accountability.e008_2_external_feedback_integration": "E008.2: External feedback integration",
    "accountability.e009_1_third_party_access_monitoring": "E009.1: Third-party access monitoring",
    "accountability.e010_1_acceptable_use_policy": "E010.1: AI acceptable use policy",
    "accountability.e010_2_aup_violation_detection": "E010.2: AUP violation detection",
    "accountability.e010_3_user_notification_for_aup_breaches": "E010.3: User notification for AUP breaches",
    "accountability.e010_4_guardrails_enforcing_acceptable_use": "E010.4: Guardrails enforcing acceptable use",
    "accountability.e011_1_ai_processing_locations": "E011.1: AI processing locations record",
    "accountability.e011_2_data_transfer_compliance": "E011.2: Data transfer compliance",
    "accountability.e012_1_regulatory_compliance_reviews": "E012.1: Regulatory compliance reviews",
    "accountability.e013_1_quality_objectives_risk_management": "E013.1: Quality objectives and risk management",
    "accountability.e013_2_change_management_procedures": "E013.2: Change management procedures",
    "accountability.e013_3_issue_tracking_monitoring": "E013.3: Issue tracking and monitoring",
    "accountability.e013_4_data_management_procedures": "E013.4: Data management procedures",
    "accountability.e013_5_stakeholder_communication_procedures": "E013.5: Stakeholder communication procedures",
    "accountability.e015_1_logging_implementation": "E015.1: Model activity logging implementation",
    "accountability.e015_2_log_storage": "E015.2: Log storage and retention",
    "accountability.e015_3_log_integrity_protection": "E015.3: Log integrity protection",
    "accountability.e016_1_text_ai_disclosure": "E016.1: Text AI disclosure",
    "accountability.e016_2_voice_ai_disclosure": "E016.2: Voice AI disclosure",
    "accountability.e016_3_labelling_ai_generated_content": "E016.3: Labelling AI-generated content",
    "accountability.e016_4_automation_ai_disclosure": "E016.4: Automation AI disclosure",
    "accountability.e016_5_system_response_to_ai_inquiry": "E016.5: System response to AI inquiry",
    "accountability.e017_1_transparency_policy": "E017.1: System transparency policy",
    "accountability.e017_2_model_cards_system_documentation": "E017.2: Model cards and system documentation",
    "accountability.e017_3_transparency_report_sharing_policy": "E017.3: Transparency report sharing policy",
    # ── F. Society ─────────────────────────────────────────────────────────
    "society.f001_1_foundation_model_cyber_capabilities": "F001.1: Foundation model cyber capabilities documentation",
    "society.f001_2_cyber_use_detection": "F001.2: Cyber use detection implementation",
    "society.f002_1_foundation_model_cbrn_capabilities": "F002.1: Foundation model CBRN capabilities documentation",
    "society.f002_2_catastrophic_misuse_monitoring": "F002.2: Catastrophic misuse monitoring",
}


# ---------------------------------------------------------------------------
# Tier registry and selection helpers
# ---------------------------------------------------------------------------

TIERS: dict[str, dict[str, Any]] = {
    "essential": ESSENTIAL_BASELINE,
    "ai_standard": AI_STANDARD_BASELINE,
    "ai_comprehensive": AI_COMPREHENSIVE_BASELINE,
}


def select_baseline_tier(ai_enabled: bool, business_criticality: str) -> str:
    """Select appropriate baseline tier based on project characteristics.

    Args:
        ai_enabled: Whether the project uses AI.
        business_criticality: One of: low, moderate, high, mission_critical.

    Returns:
        Tier name: 'essential', 'ai_standard', or 'ai_comprehensive'.
    """
    if not ai_enabled:
        return "essential"
    if business_criticality in ("high", "mission_critical", "critical"):
        return "ai_comprehensive"
    return "ai_standard"


def get_baseline(tier: str) -> dict[str, Any]:
    """Get baseline dict for a tier."""
    return TIERS.get(tier, ESSENTIAL_BASELINE)


def get_recommended_baseline(
    ai_enabled: bool,
    business_criticality: str,
) -> dict[str, Any]:
    """Get the recommended baseline for project characteristics."""
    tier = select_baseline_tier(ai_enabled, business_criticality)
    return get_baseline(tier)


def get_all_baselines() -> dict[str, dict[str, Any]]:
    """Get all three tier baselines."""
    return TIERS.copy()
