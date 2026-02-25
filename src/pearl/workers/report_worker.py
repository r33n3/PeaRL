"""Worker for report generation jobs."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.finding import FindingRow
from pearl.db.models.report import ReportRow
from pearl.services.id_generator import generate_id
from pearl.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class GenerateReportWorker(BaseWorker):
    """Generate a project security report and store as a ReportRow."""

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        project_id: str = payload.get("project_id", "")
        report_type: str = payload.get("report_type", "security_summary")
        environment: str = payload.get("environment", "all")
        trace_id: str = payload.get("trace_id", job_id)

        if not project_id:
            raise ValueError("payload must include project_id")

        # Gather findings for the project
        stmt = select(FindingRow).where(FindingRow.project_id == project_id)
        if environment != "all":
            stmt = stmt.where(FindingRow.environment == environment)
        result = await session.execute(stmt)
        findings = list(result.scalars().all())

        # Count by severity
        severity_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for f in findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1
            status_counts[f.status] = status_counts.get(f.status, 0) + 1

        report_id = generate_id("rpt_")
        now = datetime.now(timezone.utc)

        content = {
            "report_id": report_id,
            "project_id": project_id,
            "report_type": report_type,
            "environment": environment,
            "generated_at": now.isoformat(),
            "summary": {
                "total_findings": len(findings),
                "by_severity": severity_counts,
                "by_status": status_counts,
            },
            "findings": [
                {
                    "finding_id": f.finding_id,
                    "title": f.title,
                    "severity": f.severity,
                    "status": f.status,
                    "category": f.category,
                    "environment": f.environment,
                }
                for f in findings
            ],
        }

        report = ReportRow(
            report_id=report_id,
            project_id=project_id,
            report_type=report_type,
            status="completed",
            format="json",
            content=content,
            artifact_ref=None,
            trace_id=trace_id,
            generated_at=now,
        )
        session.add(report)
        await session.flush()

        logger.info("Generated report %s (type=%s, project=%s)", report_id, report_type, project_id)

        return {
            "result_refs": [
                {
                    "ref_id": report_id,
                    "kind": "report",
                    "summary": f"{report_type} report ({len(findings)} findings)",
                }
            ]
        }
