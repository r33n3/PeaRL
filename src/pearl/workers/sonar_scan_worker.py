"""Worker that runs sonar-scanner via Docker and ingests findings into PeaRL."""

from __future__ import annotations

import asyncio
import structlog
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.workers.base import BaseWorker

logger = structlog.get_logger(__name__)

# Path to the docker-compose.yaml at the repo root
_COMPOSE_FILE = Path(__file__).resolve().parents[4] / "docker-compose.yaml"


class SonarScanWorker(BaseWorker):
    """Runs sonar-scanner in Docker against a target path and ingests results."""

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        target_path: str = payload.get("target_path", "")
        project_id: str = payload.get("project_id", "")

        if not target_path:
            raise ValueError("payload must include target_path")
        if not project_id:
            raise ValueError("payload must include project_id")

        logger.info(
            "SonarScanWorker: starting scan job_id=%s target=%s project=%s",
            job_id,
            target_path,
            project_id,
        )

        # Build docker compose run command
        cmd = [
            "docker",
            "compose",
            "-f",
            str(_COMPOSE_FILE),
            "run",
            "--rm",
            "-e",
            f"SONAR_TOKEN={settings.sonar_token}",
            "-e",
            "SONAR_HOST_URL=http://sonarqube:9000",
            "-v",
            f"{target_path}:/usr/src",
            "sonar-scanner",
        ]

        logger.info("SonarScanWorker: executing %s", " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=300.0
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                raise RuntimeError(
                    f"sonar-scanner timed out after 300s for target {target_path}"
                )

            exit_code = proc.returncode
            stdout = stdout_bytes.decode("utf-8", errors="replace")
            stderr = stderr_bytes.decode("utf-8", errors="replace")

            logger.info(
                "SonarScanWorker: scanner exit_code=%d job_id=%s",
                exit_code,
                job_id,
            )

            if exit_code != 0:
                raise RuntimeError(
                    f"sonar-scanner exited with code {exit_code}. stderr: {stderr[:2000]}"
                )

        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to run sonar-scanner: {exc}") from exc

        # Pull findings after successful scan
        findings_pulled = 0
        quality_gate_status = "UNKNOWN"

        try:
            from pearl.integrations.adapters.sonarqube import SonarQubeAdapter
            from pearl.integrations.config import AuthConfig, IntegrationEndpoint
            from pearl.models.enums import IntegrationCategory, IntegrationType
            from pearl.repositories.finding_repo import FindingRepository
            from pearl.repositories.integration_repo import IntegrationEndpointRepository
            from pearl.services.id_generator import generate_id

            integration_repo = IntegrationEndpointRepository(session)

            # Try project-level endpoint, then org-level
            endpoints = await integration_repo.list_by_project(project_id)
            row = next((e for e in endpoints if e.adapter_type == "sonarqube"), None)
            if row is None:
                row = await integration_repo.get_org_by_adapter_type("sonarqube")

            if row is not None:
                auth_data = row.auth_config or {}
                endpoint = IntegrationEndpoint(
                    endpoint_id=row.endpoint_id,
                    name=row.name,
                    adapter_type=row.adapter_type,
                    integration_type=IntegrationType(row.integration_type),
                    category=IntegrationCategory(row.category),
                    base_url=row.base_url,
                    auth=AuthConfig(**auth_data) if auth_data else AuthConfig(),
                    project_mapping=row.project_mapping,
                    enabled=row.enabled,
                    labels=row.labels,
                )

                adapter = SonarQubeAdapter()
                findings = await adapter.pull_findings(endpoint, since=None)

                finding_repo = FindingRepository(session)
                from sqlalchemy import select
                from pearl.db.models.finding import FindingRow

                for nf in findings:
                    stmt = select(FindingRow).where(
                        FindingRow.project_id == project_id,
                    ).where(
                        FindingRow.source["raw_record_ref"].as_string() == nf.external_id,
                    ).where(
                        FindingRow.source["tool_name"].as_string() == "sonarqube",
                    ).limit(1)
                    result = await session.execute(stmt)
                    existing = result.scalar_one_or_none()

                    if existing:
                        existing.title = nf.title
                        existing.severity = nf.severity
                        existing.category = nf.category
                        existing.full_data = nf.raw_record or {}
                        existing.cwe_ids = nf.cwe_ids
                        await session.flush()
                    else:
                        finding_id = generate_id("find_")
                        await finding_repo.create(
                            finding_id=finding_id,
                            project_id=project_id,
                            environment="dev",
                            category=nf.category,
                            severity=nf.severity,
                            title=nf.title,
                            source={
                                "tool_name": "sonarqube",
                                "tool_type": nf.source_type,
                                "trust_label": "trusted_external_registered",
                                "raw_record_ref": nf.external_id,
                            },
                            full_data=nf.raw_record or {},
                            normalized=False,
                            detected_at=nf.detected_at,
                            batch_id=None,
                            cwe_ids=nf.cwe_ids,
                            compliance_refs=None,
                            status="open",
                        )

                findings_pulled = len(findings)

                labels = endpoint.labels or {}
                project_key = labels.get("project_key", project_id)
                qg = await adapter.get_quality_gate_status(endpoint, project_key)
                quality_gate_status = qg.get("status", "UNKNOWN")

                # Update last_sync
                row.last_scanned_at = datetime.now(timezone.utc)
                row.last_scan_status = "success"
                await session.flush()

        except Exception as exc:
            logger.warning(
                "SonarScanWorker: post-scan ingest failed job_id=%s: %s", job_id, exc
            )

        logger.info(
            "SonarScanWorker: complete job_id=%s findings=%d quality_gate=%s",
            job_id,
            findings_pulled,
            quality_gate_status,
        )

        return {
            "result_refs": [
                {
                    "ref_id": job_id,
                    "kind": "sonar_scan",
                    "summary": f"SonarQube scan completed: {findings_pulled} findings ingested",
                    "exit_code": exit_code,
                    "findings_pulled": findings_pulled,
                    "quality_gate": quality_gate_status,
                }
            ]
        }
