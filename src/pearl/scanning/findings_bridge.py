"""Bridge between MASS-style analyzer findings and PeaRL's finding ingestion format."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pearl.scanning.types import AttackCategory, ScanSeverity
from pearl.scanning.compliance.mappings import get_mapping_for_category

# RAI categories that map to "responsible_ai" instead of "security"
_RAI_CATEGORIES = {
    AttackCategory.BIAS,
    AttackCategory.TOXICITY,
    AttackCategory.MISINFORMATION,
    AttackCategory.HALLUCINATION,
}

_SEVERITY_MAP = {
    ScanSeverity.CRITICAL: "critical",
    ScanSeverity.HIGH: "high",
    ScanSeverity.MEDIUM: "moderate",  # PeaRL uses "moderate" not "medium"
    ScanSeverity.LOW: "low",
    ScanSeverity.INFO: "low",
}

_CONFIDENCE_MAP = {
    # confidence float ranges to PeaRL confidence string
    # >= 0.8 -> high, >= 0.5 -> medium, else -> low
}


def _map_confidence(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    elif confidence >= 0.5:
        return "medium"
    return "low"


def _build_compliance_refs(category: AttackCategory) -> dict[str, list[str]]:
    """Build compliance_refs dict from attack category mapping."""
    mapping = get_mapping_for_category(category)
    if not mapping:
        return {}
    refs: dict[str, list[str]] = {}
    if mapping.owasp_llm:
        refs["owasp_llm_top10"] = mapping.owasp_llm
    if mapping.mitre_atlas:
        refs["mitre_atlas"] = mapping.mitre_atlas
    if mapping.nist_ai_rmf:
        refs["nist_ai_rmf"] = mapping.nist_ai_rmf
    if mapping.eu_ai_act:
        refs["eu_ai_act"] = mapping.eu_ai_act
    return refs


def convert_analyzer_finding(
    finding,  # AnalyzerFinding
    project_id: str,
    environment: str = "dev",
    analyzer_name: str = "unknown",
    finding_id: str | None = None,
) -> dict[str, Any]:
    """Convert a single AnalyzerFinding to PeaRL finding ingest format."""
    from pearl.services.id_generator import generate_id

    fid = finding_id or generate_id("find_")
    category = "responsible_ai" if finding.category in _RAI_CATEGORIES else "security"

    return {
        "finding_id": fid,
        "source": {
            "tool_name": f"pearl_scan_{analyzer_name}",
            "tool_type": "mass",
            "trust_label": "trusted_internal",
        },
        "project_id": project_id,
        "environment": environment,
        "category": category,
        "severity": _SEVERITY_MAP.get(finding.severity, "moderate"),
        "confidence": _map_confidence(finding.confidence),
        "title": finding.title,
        "description": finding.description,
        "affected_components": [finding.component_name] if finding.component_name else [],
        "cwe_ids": finding.cwe_ids or [],
        "compliance_refs": _build_compliance_refs(finding.category),
        "detected_at": datetime.now(timezone.utc).isoformat(),
        "status": "open",
    }


def convert_scan_result(
    result,  # AnalyzerResult
    project_id: str,
    environment: str = "dev",
) -> dict[str, Any]:
    """Convert a full AnalyzerResult to PeaRL findings ingest batch format."""
    from pearl.services.id_generator import generate_id

    findings = []
    for finding in result.findings:
        findings.append(convert_analyzer_finding(
            finding,
            project_id=project_id,
            environment=environment,
            analyzer_name=result.analyzer_name,
        ))

    return {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": generate_id("batch_"),
            "source_system": f"pearl_scan_{result.analyzer_name}",
            "connector_version": "1.0.0",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "trust_label": "trusted_internal",
        },
        "findings": findings,
        "options": {
            "normalize_on_ingest": True,
            "strict_validation": False,
            "quarantine_on_error": True,
        },
    }


def convert_multiple_results(
    results: list,  # list[AnalyzerResult]
    project_id: str,
    environment: str = "dev",
) -> dict[str, Any]:
    """Convert multiple analyzer results into a single PeaRL ingest batch."""
    from pearl.services.id_generator import generate_id

    all_findings = []
    analyzer_names = []
    for result in results:
        analyzer_names.append(result.analyzer_name)
        for finding in result.findings:
            all_findings.append(convert_analyzer_finding(
                finding,
                project_id=project_id,
                environment=environment,
                analyzer_name=result.analyzer_name,
            ))

    return {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": generate_id("batch_"),
            "source_system": "pearl_scan",
            "connector_version": "1.0.0",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "trust_label": "trusted_internal",
        },
        "findings": all_findings,
        "options": {
            "normalize_on_ingest": True,
            "strict_validation": False,
            "quarantine_on_error": True,
        },
    }
