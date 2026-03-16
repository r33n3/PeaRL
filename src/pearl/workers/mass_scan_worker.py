"""Worker that triggers MASS 2.0 scans and ingests findings into PeaRL."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.repositories.scan_target_repo import ScanTargetRepository
from pearl.scanning.mass_bridge import MassClient, mass_finding_to_pearl
from pearl.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class MassScanWorker(BaseWorker):
    """Triggers a MASS 2.0 scan and ingests its findings."""

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        project_id: str = payload.get("project_id", "")
        target_url: str = payload.get("target_url", "")
        target_type: str = payload.get("target_type", "full")
        scan_target_id: str | None = payload.get("scan_target_id")

        if not project_id:
            raise ValueError("payload must include project_id")
        if not target_url:
            raise ValueError("payload must include target_url")

        logger.info(
            "MassScanWorker: submitting scan target_id=%s url=%s",
            scan_target_id,
            target_url,
        )

        # Load the scan target row for status updates
        target_row = None
        if scan_target_id:
            target_repo = ScanTargetRepository(session)
            target_row = await target_repo.get(scan_target_id)

        try:
            client = MassClient(
                base_url=settings.mass_url,
                api_key=settings.mass_api_key,
            )

            scan_id = await client.create_scan(
                target_url=target_url,
                target_type=target_type,
                project_id=project_id,
            )

            report = await client.wait_for_completion(
                scan_id,
                timeout=settings.mass_scan_timeout,
            )

            raw_findings = report.get("findings") or []
            findings = [
                mass_finding_to_pearl(f, project_id=project_id)
                for f in raw_findings
            ]
            batch_id = f"mass_{scan_id}"

            # Ingest findings using the same repository pattern as scan_worker.py
            if findings:
                from pearl.repositories.finding_repo import (
                    FindingBatchRepository,
                    FindingRepository,
                )
                from pearl.services.id_generator import generate_id

                finding_repo = FindingRepository(session)
                accepted = 0
                quarantined = 0

                for finding_data in findings:
                    try:
                        finding_id = generate_id("find_")
                        await finding_repo.create(
                            finding_id=finding_id,
                            project_id=finding_data["project_id"],
                            environment=payload.get("environment", "dev"),
                            category=finding_data["category"],
                            severity=finding_data["severity"].lower(),
                            title=finding_data["title"],
                            source={
                                "tool_name": finding_data["tool_name"],
                                "tool_type": "mass",
                                "trust_label": "trusted_external",
                            },
                            full_data=finding_data,
                            normalized=False,
                            detected_at=datetime.now(timezone.utc),
                            batch_id=batch_id,
                            cwe_ids=finding_data.get("cwe_ids"),
                            compliance_refs=finding_data.get("compliance_refs"),
                            status=finding_data.get("status", "open"),
                        )
                        accepted += 1
                    except Exception as exc:
                        logger.warning("Failed to persist MASS finding: %s", exc)
                        quarantined += 1

                batch_repo = FindingBatchRepository(session)
                await batch_repo.create(
                    batch_id=batch_id,
                    source_system="mass_scan",
                    trust_label="trusted_external",
                    accepted_count=accepted,
                    quarantined_count=quarantined,
                    normalized_count=0,
                )
                await session.flush()

            # Update scan target status
            if target_row:
                target_row.last_scanned_at = datetime.now(timezone.utc)
                target_row.last_scan_status = "success"
                await session.flush()

            logger.info(
                "MassScanWorker: complete scan_id=%s batch_id=%s findings=%d",
                scan_id,
                batch_id,
                len(findings),
            )

            return {
                "result_refs": [
                    {
                        "ref_id": batch_id,
                        "kind": "scan_batch",
                        "summary": f"MASS scan completed: {len(findings)} findings",
                        "scan_id": scan_id,
                        "total_findings": len(findings),
                        "risk_score": report.get("risk_score"),
                        "status": report.get("status"),
                    }
                ]
            }

        except Exception as exc:
            if target_row:
                target_row.last_scanned_at = datetime.now(timezone.utc)
                target_row.last_scan_status = "error"
                await session.flush()
            raise exc
