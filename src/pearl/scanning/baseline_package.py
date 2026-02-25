"""Tiered governance baseline packages for PeaRL projects.

Three tiers:
- Essential: All projects regardless of AI usage
- AI-Standard: AI-enabled projects (low/moderate criticality)
- AI-Comprehensive: High-risk AI projects (high/critical criticality)

Selection is automatic based on app_spec.ai_enabled and business_criticality.

Each tier is defined as a complete, self-contained dict.  Higher tiers
include all keys from lower tiers rather than relying on shallow ``**``
unpacking, which would silently drop nested sub-keys when a higher-tier
dict redefines a top-level defaults section.
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
        "coding": {
            "secure_coding_standard_required": True,
            "secret_hardcoding_forbidden": True,
            "dependency_pinning_required": True,
        },
        "logging": {
            "structured_logging_required": True,
            "pii_in_logs_forbidden_by_default": True,
            "security_events_minimum": [
                "auth_failure",
                "data_access",
                "config_change",
            ],
        },
        "iam": {
            "least_privilege_required": True,
            "wildcard_permissions_forbidden_by_default": True,
        },
        "network": {
            "outbound_connectivity_must_be_declared": True,
            "deny_by_default_preferred": True,
        },
        "testing": {
            "unit_tests_required": True,
            "security_tests_baseline_required": True,
        },
        "security_review": {
            "security_review_required": True,
        },
        "artifacts": {
            "architecture_diagram_required_after_scan": True,
            "threat_model_diagram_required_after_scan": True,
            "diagram_format": "drawio",
        },
    },
}


# ---------------------------------------------------------------------------
# AI-Standard — AI-enabled projects at low / moderate business criticality
# ---------------------------------------------------------------------------

AI_STANDARD_BASELINE: dict[str, Any] = {
    "schema_version": "1.1",
    "kind": "PearlOrgBaseline",
    "baseline_id": "orgb_ai_standard_v1",
    "org_name": "PeaRL Recommended Baseline \u2014 AI-Standard",
    "tier": "ai_standard",
    "defaults": {
        # --- inherited from Essential (repeated for completeness) ---
        "coding": {
            "secure_coding_standard_required": True,
            "secret_hardcoding_forbidden": True,
            "dependency_pinning_required": True,
        },
        "logging": {
            "structured_logging_required": True,
            "pii_in_logs_forbidden_by_default": True,
            "security_events_minimum": [
                "auth_failure",
                "data_access",
                "config_change",
            ],
        },
        "iam": {
            "least_privilege_required": True,
            "wildcard_permissions_forbidden_by_default": True,
        },
        "network": {
            "outbound_connectivity_must_be_declared": True,
            "deny_by_default_preferred": True,
        },
        # --- AI-Standard additions / overrides ---
        "responsible_ai": {
            "ai_use_disclosure_required_for_user_facing": True,
            "model_provenance_logging_required": True,
            "human_oversight_required_for_high_impact_actions": True,
            "fairness_review_required_when_user_impact_is_material": False,
        },
        "testing": {
            "unit_tests_required": True,
            "security_tests_baseline_required": True,
            "rai_evals_required_for_ai_enabled_apps": True,
        },
        "ai_security": {
            "prompt_injection_defense_required": True,
            "output_filtering_required": True,
            "tool_restriction_policy_required": True,
        },
        "scanning": {
            "context_analysis_required": True,
            "mcp_analysis_required": True,
            "workflow_analysis_required": True,
            "attack_surface_mapping_required": True,
        },
        "compliance_frameworks": {
            "owasp_llm_top10_assessment_required": True,
        },
        "security_review": {
            "security_review_required": True,
            "security_review_must_cover_ai_components": True,
        },
        "artifacts": {
            "architecture_diagram_required_after_scan": True,
            "threat_model_diagram_required_after_scan": True,
            "diagram_format": "drawio",
            "updated_diagrams_required_for_promotion": True,
        },
    },
}


# ---------------------------------------------------------------------------
# AI-Comprehensive — high-risk AI projects (high / critical criticality)
# ---------------------------------------------------------------------------

AI_COMPREHENSIVE_BASELINE: dict[str, Any] = {
    "schema_version": "1.1",
    "kind": "PearlOrgBaseline",
    "baseline_id": "orgb_ai_comprehensive_v1",
    "org_name": "PeaRL Recommended Baseline \u2014 AI-Comprehensive",
    "tier": "ai_comprehensive",
    "defaults": {
        # --- inherited from Essential (repeated for completeness) ---
        "coding": {
            "secure_coding_standard_required": True,
            "secret_hardcoding_forbidden": True,
            "dependency_pinning_required": True,
        },
        "logging": {
            "structured_logging_required": True,
            "pii_in_logs_forbidden_by_default": True,
            "security_events_minimum": [
                "auth_failure",
                "data_access",
                "config_change",
            ],
        },
        "iam": {
            "least_privilege_required": True,
            "wildcard_permissions_forbidden_by_default": True,
        },
        "network": {
            "outbound_connectivity_must_be_declared": True,
            "deny_by_default_preferred": True,
        },
        # --- inherited from AI-Standard (repeated for completeness) ---
        "responsible_ai": {
            "ai_use_disclosure_required_for_user_facing": True,
            "model_provenance_logging_required": True,
            "human_oversight_required_for_high_impact_actions": True,
            # upgraded from False (AI-Standard) to True (AI-Comprehensive)
            "fairness_review_required_when_user_impact_is_material": True,
        },
        "testing": {
            "unit_tests_required": True,
            "security_tests_baseline_required": True,
            "rai_evals_required_for_ai_enabled_apps": True,
        },
        # --- AI-Comprehensive additions / overrides ---
        "ai_security": {
            "prompt_injection_defense_required": True,
            "output_filtering_required": True,
            "pii_redaction_required": True,
            "tool_restriction_policy_required": True,
            "model_access_restriction_required": True,
            "rate_limiting_required": True,
            "content_moderation_required": True,
            "audit_logging_required": True,
            "encryption_in_transit_required": True,
        },
        "scanning": {
            "context_analysis_required": True,
            "mcp_analysis_required": True,
            "workflow_analysis_required": True,
            "attack_surface_mapping_required": True,
            "model_file_scanning_required": True,
            "rag_pipeline_analysis_required": True,
        },
        "compliance_frameworks": {
            "owasp_llm_top10_assessment_required": True,
            "mitre_atlas_assessment_required": True,
            "nist_ai_rmf_assessment_required": True,
            "eu_ai_act_assessment_when_applicable": True,
        },
        "security_review": {
            "security_review_required": True,
            "security_review_must_cover_ai_components": True,
            "security_review_recurrence": "per_release",
        },
        "artifacts": {
            "architecture_diagram_required_after_scan": True,
            "threat_model_diagram_required_after_scan": True,
            "diagram_format": "drawio",
            "updated_diagrams_required_for_promotion": True,
            "updated_diagrams_required_for_prod": True,
            "diagram_must_reflect_current_scan_state": True,
        },
    },
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
