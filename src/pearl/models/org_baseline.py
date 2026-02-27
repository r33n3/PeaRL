"""Pydantic models for OrgBaseline — AIUC-1 structured governance baseline."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.common import Integrity


# ---------------------------------------------------------------------------
# A. Data & Privacy sub-controls
# ---------------------------------------------------------------------------

class DataPrivacyDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # A001: Establish input data policy
    a001_1_policy_documentation: bool | None = None
    a001_2_data_retention_implementation: bool | None = None
    a001_3_data_subject_right_processes: bool | None = None
    # A002: Establish output data policy
    a002_1_output_usage_ownership_policy: bool | None = None
    # A003: Limit AI agent data collection
    a003_1_data_collection_scoping: bool | None = None
    a003_2_alerting_for_auth_failures: bool | None = None
    a003_3_authorization_system_integration: bool | None = None
    # A004: Protect IP & trade secrets
    a004_1_user_guidance_on_confidential_info: bool | None = None
    a004_2_foundational_model_ip_protections: bool | None = None
    a004_3_ip_detection_implementation: bool | None = None
    a004_4_ip_disclosure_monitoring: bool | None = None
    # A005: Prevent cross-customer data exposure
    a005_1_consent_for_combined_data: bool | None = None
    a005_2_customer_data_isolation: bool | None = None
    a005_3_privacy_enhancing_controls: bool | None = None
    # A006: Prevent PII leakage
    a006_1_pii_detection_filtering: bool | None = None
    a006_2_pii_access_controls: bool | None = None
    a006_3_dlp_system_integration: bool | None = None
    # A007: Prevent IP violations
    a007_1_model_provider_ip_protections: bool | None = None
    a007_2_ip_infringement_filtering: bool | None = None
    a007_3_user_facing_ip_notices: bool | None = None


# ---------------------------------------------------------------------------
# B. Security sub-controls
# ---------------------------------------------------------------------------

class SecurityDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # B001: Third-party adversarial robustness testing
    b001_1_adversarial_testing_report: bool | None = None
    b001_2_security_program_integration: bool | None = None
    # B002: Detect adversarial input
    b002_1_adversarial_input_detection_alerting: bool | None = None
    b002_2_adversarial_incident_response: bool | None = None
    b002_3_detection_config_updates: bool | None = None
    b002_4_preprocessing_adversarial_detection: bool | None = None
    b002_5_ai_security_alerts: bool | None = None
    # B003: Manage public release of technical details
    b003_1_technical_disclosure_guidelines: bool | None = None
    b003_2_public_disclosure_approval_records: bool | None = None
    # B004: Prevent AI endpoint scraping
    b004_1_anomalous_usage_detection: bool | None = None
    b004_2_rate_limits: bool | None = None
    b004_3_external_pentest_ai_endpoints: bool | None = None
    b004_4_vulnerability_remediation: bool | None = None
    # B005: Implement real-time input filtering
    b005_1_input_filtering: bool | None = None
    b005_2_input_moderation_approach: bool | None = None
    b005_3_warning_for_blocked_inputs: bool | None = None
    b005_4_input_filtering_logs: bool | None = None
    b005_5_input_filter_performance: bool | None = None
    # B006: Prevent unauthorized AI agent actions
    b006_1_agent_service_access_restrictions: bool | None = None
    b006_2_agent_security_monitoring_alerting: bool | None = None
    # B007: Enforce user access privileges to AI systems
    b007_1_user_access_controls: bool | None = None
    b007_2_access_reviews: bool | None = None
    # B008: Protect model deployment environment
    b008_1_model_access_controls: bool | None = None
    b008_2_api_deployment_security: bool | None = None
    b008_3_model_hosting_security: bool | None = None
    b008_4_model_integrity_verification: bool | None = None
    # B009: Limit output over-exposure
    b009_1_output_volume_limits: bool | None = None
    b009_2_user_output_notices: bool | None = None
    b009_3_output_precision_controls: bool | None = None


# ---------------------------------------------------------------------------
# C. Safety sub-controls
# ---------------------------------------------------------------------------

class SafetyDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # C001: Define AI risk taxonomy
    c001_1_risk_taxonomy: bool | None = None
    c001_2_risk_taxonomy_reviews: bool | None = None
    # C002: Conduct pre-deployment testing
    c002_1_pre_deployment_test_approval: bool | None = None
    c002_2_sdlc_integration: bool | None = None
    c002_3_vulnerability_scan_results: bool | None = None
    # C003: Prevent harmful outputs
    c003_1_harmful_output_filtering: bool | None = None
    c003_2_guardrails_for_high_risk_advice: bool | None = None
    c003_3_guardrails_for_biased_outputs: bool | None = None
    c003_4_filtering_performance_benchmarks: bool | None = None
    # C004: Prevent out-of-scope outputs
    c004_1_out_of_scope_guardrails: bool | None = None
    c004_2_out_of_scope_attempt_logs: bool | None = None
    c004_3_user_guidance_on_scope: bool | None = None
    # C005: Prevent customer-defined high risk outputs
    c005_1_risk_detection_response: bool | None = None
    c005_2_human_review_workflows: bool | None = None
    c005_3_automated_response_mechanisms: bool | None = None
    # C006: Prevent output vulnerabilities
    c006_1_output_sanitization: bool | None = None
    c006_2_warning_labels_untrusted_content: bool | None = None
    c006_3_adversarial_output_detection: bool | None = None
    # C007: Flag high risk outputs
    c007_1_high_risk_criteria_definition: bool | None = None
    c007_2_high_risk_detection_mechanisms: bool | None = None
    c007_3_human_review_for_high_risk: bool | None = None
    # C008: Monitor AI risk categories
    c008_1_risk_monitoring_logs: bool | None = None
    c008_2_monitoring_findings_documentation: bool | None = None
    c008_4_security_tooling_integration: bool | None = None
    # C009: Real-time feedback and intervention
    c009_1_user_intervention_mechanisms: bool | None = None
    c009_2_feedback_intervention_reviews: bool | None = None
    # C010/C011/C012: Third-party testing
    c010_1_harmful_output_testing_report: bool | None = None
    c011_1_outofscope_output_testing_report: bool | None = None
    c012_1_customer_risk_testing_report: bool | None = None


# ---------------------------------------------------------------------------
# D. Reliability sub-controls
# ---------------------------------------------------------------------------

class ReliabilityDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # D001: Prevent hallucinated outputs
    d001_1_groundedness_filter: bool | None = None
    d001_2_user_citations_source_attribution: bool | None = None
    d001_3_user_uncertainty_labels: bool | None = None
    # D002: Third-party hallucination testing
    d002_1_hallucination_testing_report: bool | None = None
    # D003: Restrict unsafe tool calls
    d003_1_tool_authorization_validation: bool | None = None
    d003_2_rate_limits_for_tools: bool | None = None
    d003_3_tool_call_log: bool | None = None
    d003_4_human_approval_workflows: bool | None = None
    d003_5_tool_call_log_reviews: bool | None = None
    # D004: Third-party tool call testing
    d004_1_tool_call_testing_report: bool | None = None


# ---------------------------------------------------------------------------
# E. Accountability sub-controls
# ---------------------------------------------------------------------------

class AccountabilityDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # E001: AI failure plan for security breaches
    e001_1_security_breach_failure_plan: bool | None = None
    # E002: AI failure plan for harmful outputs
    e002_1_harmful_output_failure_plan: bool | None = None
    e002_2_harmful_output_failure_procedures: bool | None = None
    # E003: AI failure plan for hallucinations
    e003_1_hallucination_failure_plan: bool | None = None
    e003_2_hallucination_failure_procedures: bool | None = None
    # E004: Assign accountability (E007 merged here in Q1 2026)
    e004_1_change_approval_policy_records: bool | None = None
    e004_2_code_signing_implementation: bool | None = None
    # E005: Assess cloud vs on-prem
    e005_1_deployment_decisions: bool | None = None
    # E006: Vendor due diligence
    e006_1_vendor_due_diligence: bool | None = None
    # E008: Review internal processes
    e008_1_internal_review_documentation: bool | None = None
    e008_2_external_feedback_integration: bool | None = None
    # E009: Monitor third-party access
    e009_1_third_party_access_monitoring: bool | None = None
    # E010: Establish AI acceptable use policy
    e010_1_acceptable_use_policy: bool | None = None
    e010_2_aup_violation_detection: bool | None = None
    e010_3_user_notification_for_aup_breaches: bool | None = None
    e010_4_guardrails_enforcing_acceptable_use: bool | None = None
    # E011: Record processing locations
    e011_1_ai_processing_locations: bool | None = None
    e011_2_data_transfer_compliance: bool | None = None
    # E012: Document regulatory compliance
    e012_1_regulatory_compliance_reviews: bool | None = None
    # E013: Quality management system
    e013_1_quality_objectives_risk_management: bool | None = None
    e013_2_change_management_procedures: bool | None = None
    e013_3_issue_tracking_monitoring: bool | None = None
    e013_4_data_management_procedures: bool | None = None
    e013_5_stakeholder_communication_procedures: bool | None = None
    # E015: Log model activity
    e015_1_logging_implementation: bool | None = None
    e015_2_log_storage: bool | None = None
    e015_3_log_integrity_protection: bool | None = None
    # E016: Implement AI disclosure mechanisms
    e016_1_text_ai_disclosure: bool | None = None
    e016_2_voice_ai_disclosure: bool | None = None
    e016_3_labelling_ai_generated_content: bool | None = None
    e016_4_automation_ai_disclosure: bool | None = None
    e016_5_system_response_to_ai_inquiry: bool | None = None
    # E017: System transparency policy (E014 merged here in Q1 2026)
    e017_1_transparency_policy: bool | None = None
    e017_2_model_cards_system_documentation: bool | None = None
    e017_3_transparency_report_sharing_policy: bool | None = None


# ---------------------------------------------------------------------------
# F. Society sub-controls
# ---------------------------------------------------------------------------

class SocietyDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # F001: Prevent AI cyber misuse
    f001_1_foundation_model_cyber_capabilities: bool | None = None
    f001_2_cyber_use_detection: bool | None = None
    # F002: Prevent catastrophic misuse (CBRN)
    f002_1_foundation_model_cbrn_capabilities: bool | None = None
    f002_2_catastrophic_misuse_monitoring: bool | None = None


# ---------------------------------------------------------------------------
# Composed OrgDefaults — all 6 AIUC-1 domains required
# ---------------------------------------------------------------------------

class OrgDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_privacy: DataPrivacyDefaults
    security: SecurityDefaults
    safety: SafetyDefaults
    reliability: ReliabilityDefaults
    accountability: AccountabilityDefaults
    society: SocietyDefaults


# ---------------------------------------------------------------------------
# Per-environment promotion requirements
# Each list contains dot-notation control references that must be True in the
# org baseline before a project may promote to that environment.
# Example: ["security.b001_1_adversarial_testing_report",
#           "data_privacy.a006_1_pii_detection_filtering"]
# ---------------------------------------------------------------------------

class EnvironmentRequirements(BaseModel):
    """Controls required to be True in the org baseline for promotion to each environment."""

    model_config = ConfigDict(extra="forbid")

    sandbox: list[str] = Field(
        default_factory=list,
        description="Controls required before promotion to sandbox",
    )
    dev: list[str] = Field(
        default_factory=list,
        description="Controls required before promotion to dev",
    )
    preprod: list[str] = Field(
        default_factory=list,
        description="Controls required before promotion to preprod",
    )
    prod: list[str] = Field(
        default_factory=list,
        description="Controls required before promotion to prod",
    )


# ---------------------------------------------------------------------------
# Root OrgBaseline document
# ---------------------------------------------------------------------------

class OrgBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    kind: Literal["PearlOrgBaseline"]
    baseline_id: str = Field(..., pattern=r"^orgb_[A-Za-z0-9_-]+$")
    org_name: str
    defaults: OrgDefaults
    environment_defaults: dict[str, Any] | None = None
    environment_requirements: EnvironmentRequirements | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    integrity: Integrity | None = None
