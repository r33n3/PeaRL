"""Findings remediation report generator."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession


async def generate_findings_remediation(project_id: str, request, db: AsyncSession) -> dict:
    """
    compliance level: counts by severity/source/status + resolved %
    full_chain level: per-finding with title, severity, source_tool, status,
                      remediation_spec_id, task_packet details, resolved_by, resolved_at
    """
    generated_at = datetime.now(timezone.utc).isoformat()

    all_findings: list = []
    try:
        from pearl.repositories.finding_repo import FindingRepository

        finding_repo = FindingRepository(db)
        # Use list_by_field to get ALL findings (including resolved) — no status filter
        from sqlalchemy import select
        from pearl.db.models.finding import FindingRow

        stmt = select(FindingRow).where(FindingRow.project_id == project_id)
        result = await db.execute(stmt)
        all_findings = list(result.scalars().all())
    except Exception:
        all_findings = []

    # Build summary counts
    by_severity: dict[str, int] = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    by_status: dict[str, int] = {"open": 0, "in_remediation": 0, "resolved": 0}
    by_source: dict[str, int] = {}
    resolved_count = 0

    for f in all_findings:
        # Severity
        sev = (f.severity or "unknown").lower()
        if sev in by_severity:
            by_severity[sev] = by_severity[sev] + 1
        else:
            by_severity[sev] = by_severity.get(sev, 0) + 1

        # Status
        status = (f.status or "open").lower()
        if status in by_status:
            by_status[status] = by_status[status] + 1
        else:
            by_status[status] = by_status.get(status, 0) + 1

        if status == "resolved":
            resolved_count += 1

        # Source
        source_data = f.source or {}
        if isinstance(source_data, dict):
            source_tool = source_data.get("tool") or source_data.get("source_tool") or "unknown"
        else:
            source_tool = str(source_data) or "unknown"
        by_source[source_tool] = by_source.get(source_tool, 0) + 1

    total = len(all_findings)
    resolved_pct = round((resolved_count / total * 100), 1) if total > 0 else 0.0

    summary: dict = {
        "total": total,
        "by_severity": by_severity,
        "by_status": by_status,
        "by_source": by_source,
        "resolved_pct": resolved_pct,
    }

    result_dict: dict = {
        "project_id": project_id,
        "detail_level": request.detail_level,
        "generated_at": generated_at,
        "summary": summary,
    }

    if request.detail_level == "full_chain":
        findings_list: list[dict] = []
        for f in all_findings:
            source_data = f.source or {}
            if isinstance(source_data, dict):
                source_tool = source_data.get("tool") or source_data.get("source_tool") or "unknown"
                artifact_refs = source_data.get("artifact_refs", [])
            else:
                source_tool = str(source_data) or "unknown"
                artifact_refs = []

            findings_list.append(
                {
                    "finding_id": f.finding_id,
                    "title": f.title,
                    "severity": f.severity,
                    "source_tool": source_tool,
                    "status": f.status,
                    "detected_at": f.detected_at.isoformat() if f.detected_at else None,
                    "remediation_spec_id": None,  # no direct FK on FindingRow
                    "task_packet_id": None,        # no direct FK on FindingRow
                    "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
                    "artifact_refs": artifact_refs,
                }
            )
        result_dict["findings"] = findings_list

    return result_dict
