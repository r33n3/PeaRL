"""Worker for scan_source jobs."""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.repositories.scan_target_repo import ScanTargetRepository
from pearl.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class ScanWorker(BaseWorker):
    """Pull findings from a scanner (Snyk, Semgrep, Trivy) via integration adapters."""

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        project_id: str = payload.get("project_id", "")
        scan_target_id: str | None = payload.get("scan_target_id")
        environment: str = payload.get("environment", "dev")

        if not project_id:
            raise ValueError("payload must include project_id")

        # Load the scan target
        target_row = None
        if scan_target_id:
            target_repo = ScanTargetRepository(session)
            target_row = await target_repo.get(scan_target_id)
            if not target_row:
                raise ValueError(f"ScanTarget '{scan_target_id}' not found")

        # Run scan and ingest findings
        try:
            from pathlib import Path
            from pearl.scanning.service import ScanningService

            service = ScanningService()

            # Use repo_url as target path if it's a local path, otherwise use "."
            target_path = "."
            if target_row and target_row.repo_url and not target_row.repo_url.startswith("http"):
                target_path = target_row.repo_url

            tool_type = target_row.tool_type if target_row else "all"
            analyzers = [tool_type] if tool_type != "all" else None

            result = await service.scan_and_ingest(
                target_path=Path(target_path),
                project_id=project_id,
                session=session,
                analyzers=analyzers,
                environment=environment,
            )

            # Update scan target status
            if target_row:
                target_row.last_scanned_at = datetime.now(timezone.utc)
                target_row.last_scan_status = "success"
                await session.flush()

            logger.info(
                "Scan complete for project %s: %d findings (batch=%s)",
                project_id, result.total_findings, result.ingested_batch_id,
            )

            return {
                "result_refs": [
                    {
                        "ref_id": result.ingested_batch_id or result.scan_id,
                        "kind": "scan_batch",
                        "summary": f"Scan completed: {result.total_findings} findings",
                        "scan_id": result.scan_id,
                        "total_findings": result.total_findings,
                    }
                ]
            }

        except Exception as exc:
            if target_row:
                target_row.last_scanned_at = datetime.now(timezone.utc)
                target_row.last_scan_status = "error"
                await session.flush()
            raise exc
