"""Worker for generate_remediation_spec jobs."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.finding import FindingRow
from pearl.db.models.remediation_spec import RemediationSpecRow
from pearl.services.id_generator import generate_id
from pearl.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class GenerateRemediationWorker(BaseWorker):
    """Generate remediation specs for a set of findings."""

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        finding_ids: list[str] = payload.get("finding_ids", [])
        project_id: str = payload.get("project_id", "")
        environment: str = payload.get("environment", "dev")
        trace_id: str = payload.get("trace_id", job_id)

        if not finding_ids:
            raise ValueError("payload must include finding_ids")

        stmt = select(FindingRow).where(FindingRow.finding_id.in_(finding_ids))
        result = await session.execute(stmt)
        findings = list(result.scalars().all())

        if not findings:
            raise ValueError(f"No findings found for ids: {finding_ids}")

        # Build remediation spec
        spec_id = generate_id("rem_")
        steps = []
        for f in findings:
            steps.append({
                "finding_id": f.finding_id,
                "title": f.title,
                "severity": f.severity,
                "category": f.category,
                "recommended_action": f.verdict.get("action", "remediate") if f.verdict else "remediate",
                "fix_available": f.fix_available,
                "references": f.full_data.get("references", []),
            })

        spec_data = {
            "spec_id": spec_id,
            "project_id": project_id,
            "environment": environment,
            "finding_count": len(findings),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "steps": steps,
        }

        spec = RemediationSpecRow(
            remediation_spec_id=spec_id,
            project_id=project_id,
            environment=environment,
            spec_data=spec_data,
            trace_id=trace_id,
        )
        session.add(spec)
        await session.flush()

        logger.info("Generated remediation spec %s for %d findings", spec_id, len(findings))

        return {
            "result_refs": [
                {
                    "ref_id": spec_id,
                    "kind": "remediation_spec",
                    "summary": f"Remediation spec for {len(findings)} findings",
                }
            ]
        }
