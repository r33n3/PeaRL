"""Bridge between normalized integration models and PeaRL canonical models.

Follows the same pattern as ``pearl.scanning.findings_bridge`` — pure conversion
functions with no side effects or DB access.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pearl.integrations.normalized import (
    NormalizedFinding,
    NormalizedNotification,
    NormalizedSecurityEvent,
    NormalizedTicket,
)


# ---------------------------------------------------------------------------
# Severity / confidence mapping
# ---------------------------------------------------------------------------

_SEVERITY_NORMALIZE: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "medium": "moderate",
    "moderate": "moderate",
    "low": "low",
    "info": "low",
    "informational": "low",
}

_PRIORITY_MAP: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "moderate": "medium",
    "low": "low",
}


def _map_severity(raw: str) -> str:
    """Normalize severity string to PeaRL RiskLevel values."""
    return _SEVERITY_NORMALIZE.get(raw.lower(), "moderate")


def _map_confidence(raw: str | None) -> str:
    """Normalize confidence string."""
    if not raw:
        return "medium"
    raw_lower = raw.lower()
    if raw_lower in ("high", "medium", "low"):
        return raw_lower
    return "medium"


# ---------------------------------------------------------------------------
# NormalizedFinding → PeaRL Finding ingest dict
# ---------------------------------------------------------------------------


def normalized_to_finding(
    nf: NormalizedFinding,
    project_id: str,
    environment: str = "dev",
    finding_id: str | None = None,
    endpoint_id: str | None = None,
) -> dict[str, Any]:
    """Convert a NormalizedFinding to PeaRL finding ingest format.

    This mirrors ``findings_bridge.convert_analyzer_finding()`` but accepts
    normalized data from external tools rather than internal AnalyzerFindings.
    """
    from pearl.services.id_generator import generate_id

    fid = finding_id or generate_id("find_")

    return {
        "finding_id": fid,
        "source": {
            "tool_name": nf.source_tool,
            "tool_type": nf.source_type,
            "connector_id": endpoint_id,
            "trust_label": "trusted_external_registered",
            "raw_record_ref": nf.external_id,
        },
        "project_id": project_id,
        "environment": environment,
        "category": nf.category,
        "severity": _map_severity(nf.severity),
        "confidence": _map_confidence(nf.confidence),
        "title": nf.title,
        "description": nf.description,
        "affected_components": nf.affected_components or [],
        "cwe_ids": nf.cwe_ids or [],
        "cve_id": nf.cve_id,
        "cvss_score": nf.cvss_score,
        "fix_available": nf.fix_available,
        "compliance_refs": {},
        "detected_at": nf.detected_at.isoformat(),
        "status": "open",
    }


def normalized_to_batch(
    findings: list[NormalizedFinding],
    project_id: str,
    environment: str = "dev",
    endpoint_id: str | None = None,
) -> dict[str, Any]:
    """Convert multiple NormalizedFindings to a PeaRL ingest batch."""
    from pearl.services.id_generator import generate_id

    source_tools = {f.source_tool for f in findings}

    return {
        "schema_version": "1.1",
        "source_batch": {
            "batch_id": generate_id("batch_"),
            "source_system": "_".join(sorted(source_tools)) if source_tools else "external",
            "connector_version": "1.0.0",
            "received_at": datetime.now(timezone.utc).isoformat(),
            "trust_label": "trusted_external_registered",
        },
        "findings": [
            normalized_to_finding(nf, project_id, environment, endpoint_id=endpoint_id)
            for nf in findings
        ],
        "options": {
            "normalize_on_ingest": True,
            "strict_validation": False,
            "quarantine_on_error": True,
        },
    }


# ---------------------------------------------------------------------------
# PeaRL Finding → outbound normalized models
# ---------------------------------------------------------------------------


def finding_to_security_event(
    finding: dict[str, Any],
    event_type: str = "finding_created",
) -> NormalizedSecurityEvent:
    """Convert a PeaRL Finding dict to a NormalizedSecurityEvent for SIEM output."""
    return NormalizedSecurityEvent(
        event_type=event_type,
        severity=finding.get("severity", "moderate"),
        timestamp=datetime.now(timezone.utc),
        project_id=finding.get("project_id", ""),
        summary=f"[{finding.get('severity', 'moderate').upper()}] {finding.get('title', 'Finding')}",
        details={
            "finding_id": finding.get("finding_id"),
            "category": finding.get("category"),
            "source": finding.get("source"),
            "affected_components": finding.get("affected_components"),
            "cve_id": finding.get("cve_id"),
            "cvss_score": finding.get("cvss_score"),
        },
        finding_ids=[finding["finding_id"]] if finding.get("finding_id") else None,
    )


def finding_to_ticket(
    finding: dict[str, Any],
    project_name: str = "",
) -> NormalizedTicket:
    """Convert a PeaRL Finding dict to a NormalizedTicket for Jira/GitHub output."""
    severity = finding.get("severity", "moderate")
    title = finding.get("title", "Security Finding")
    finding_id = finding.get("finding_id", "")

    description_parts = [
        f"**Severity:** {severity}",
        f"**Category:** {finding.get('category', 'security')}",
        f"**Finding ID:** {finding_id}",
    ]
    if finding.get("description"):
        description_parts.append(f"\n{finding['description']}")
    if finding.get("affected_components"):
        description_parts.append(f"\n**Affected:** {', '.join(finding['affected_components'])}")
    if finding.get("cve_id"):
        description_parts.append(f"**CVE:** {finding['cve_id']}")

    return NormalizedTicket(
        title=f"[{severity.upper()}] {title}" + (f" — {project_name}" if project_name else ""),
        description="\n".join(description_parts),
        priority=_PRIORITY_MAP.get(severity, "medium"),
        labels=["security", f"severity:{severity}", finding.get("category", "security")],
        finding_ids=[finding_id] if finding_id else [],
        project_id=finding.get("project_id", ""),
    )


def finding_to_notification(
    finding: dict[str, Any],
    severity_threshold: str = "high",
) -> NormalizedNotification | None:
    """Convert a PeaRL Finding to a NormalizedNotification.

    Returns None if the finding severity is below the threshold.
    """
    severity_order = {"critical": 4, "high": 3, "moderate": 2, "low": 1}
    finding_level = severity_order.get(finding.get("severity", "low"), 0)
    threshold_level = severity_order.get(severity_threshold, 3)

    if finding_level < threshold_level:
        return None

    severity = finding.get("severity", "moderate")
    title = finding.get("title", "Security Finding")
    finding_id = finding.get("finding_id", "")

    return NormalizedNotification(
        subject=f"[PeaRL] {severity.upper()} finding: {title}",
        body=(
            f"A {severity} severity finding was detected.\n\n"
            f"**Title:** {title}\n"
            f"**Finding ID:** {finding_id}\n"
            f"**Category:** {finding.get('category', 'security')}\n"
            f"**Project:** {finding.get('project_id', 'unknown')}"
        ),
        severity=severity,
        project_id=finding.get("project_id", ""),
        finding_ids=[finding_id] if finding_id else None,
    )
