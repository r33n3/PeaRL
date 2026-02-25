"""Worker for normalize_findings jobs."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.finding import FindingRow
from pearl.workers.base import BaseWorker

logger = logging.getLogger(__name__)

# Severity → base score mapping for normalization
_SEVERITY_SCORES = {
    "critical": 9.5,
    "high": 7.5,
    "medium": 5.0,
    "low": 2.5,
    "info": 0.5,
}


class NormalizeFindingsWorker(BaseWorker):
    """Normalize raw findings in a batch: score, set verdict, mark normalized."""

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        batch_id = payload.get("batch_id")
        project_id = payload.get("project_id")

        if not batch_id and not project_id:
            raise ValueError("payload must include batch_id or project_id")

        stmt = select(FindingRow).where(FindingRow.normalized.is_(False))
        if batch_id:
            stmt = stmt.where(FindingRow.batch_id == batch_id)
        elif project_id:
            stmt = stmt.where(FindingRow.project_id == project_id)

        result = await session.execute(stmt)
        findings = list(result.scalars().all())

        normalized_ids = []
        for finding in findings:
            # Compute score from severity + existing cvss_score
            severity_base = _SEVERITY_SCORES.get(finding.severity.lower(), 5.0)
            if finding.cvss_score is not None:
                computed_score = (finding.cvss_score + severity_base) / 2
            else:
                computed_score = severity_base

            finding.score = round(computed_score, 2)
            finding.normalized = True
            finding.verdict = {
                "action": "remediate" if computed_score >= 5.0 else "monitor",
                "priority": "high" if computed_score >= 7.0 else "normal",
                "normalized_at": datetime.now(timezone.utc).isoformat(),
            }
            normalized_ids.append(finding.finding_id)

        await session.flush()
        logger.info("Normalized %d findings (batch=%s)", len(normalized_ids), batch_id)

        return {
            "result_refs": [
                {
                    "ref_id": batch_id or project_id,
                    "kind": "normalized_batch",
                    "summary": f"Normalized {len(normalized_ids)} findings",
                    "finding_ids": normalized_ids,
                }
            ]
        }
