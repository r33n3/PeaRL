"""Worker that scans AgentCore CloudWatch decision logs and ingests CWD findings.

Polls the CloudWatch log group for AgentCore Cedar evaluation events starting
from the last watermark, runs the five CWD detectors, ingests any findings into
PeaRL, then advances the watermark so the next scan picks up where this one left
off.

Detection types:
  CWD-001  Policy hash drift
  CWD-002  Decision drift
  CWD-003  Agent sprawl
  CWD-004  Governance bypass
  CWD-005  Volume anomaly
"""
from __future__ import annotations

import structlog
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.integrations.agentcore.agentcore_cloudwatch import (
    AnalysisInput,
    analyse,
    extract_forbidden_actions,
    extract_registered_aliases,
    watermark_from_entries,
)
from pearl.integrations.agentcore.cloudwatch_client import CloudWatchClient
from pearl.repositories.agentcore_scan_state_repo import AgentCoreScanStateRepository
from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository
from pearl.repositories.finding_repo import FindingBatchRepository, FindingRepository
from pearl.services.id_generator import generate_id
from pearl.workers.base import BaseWorker

logger = structlog.get_logger(__name__)


class CloudWatchScanWorker(BaseWorker):
    """Scans AgentCore CloudWatch decision logs for governance anomalies.

    Payload fields:
        org_id (str):            Organisation to scan.
        project_id (str|None):   Project to associate findings with.
        environment (str):       Environment label for findings (default: prod).
        window_minutes (int):    Override the config scan window (optional).
    """

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        org_id: str = payload.get("org_id", "")
        project_id: str | None = payload.get("project_id")
        environment: str = payload.get("environment", "prod")
        window_minutes: int = int(
            payload.get("window_minutes") or settings.cloudwatch_scan_window_minutes
        )

        if not org_id:
            raise ValueError("payload must include org_id")

        # ── 1. Determine scan window from watermark ────────────────────────────
        state_repo = AgentCoreScanStateRepository(session)
        scan_state = await state_repo.get_for_org(org_id)

        now = datetime.now(timezone.utc)
        if scan_state and scan_state.log_watermark:
            start_time = scan_state.log_watermark
        else:
            start_time = now - timedelta(minutes=window_minutes)

        end_time = now

        logger.info(
            "CloudWatchScanWorker: org=%s window=%s → %s",
            org_id,
            start_time.isoformat(),
            end_time.isoformat(),
        )

        # ── 2. Query CloudWatch ────────────────────────────────────────────────
        client = CloudWatchClient(
            log_group_arn=settings.cloudwatch_log_group_arn,
            aws_region=settings.cloudwatch_aws_region,
            aws_access_key_id=settings.agentcore_aws_access_key_id,
            aws_secret_access_key=settings.agentcore_aws_secret_access_key,
            query_timeout=settings.cloudwatch_query_timeout_seconds,
        )
        entries = await client.query_decision_logs(start_time, end_time)

        logger.info(
            "CloudWatchScanWorker: retrieved %d log entries org=%s",
            len(entries),
            org_id,
        )

        # ── 3. Load active Cedar deployment for context ────────────────────────
        deploy_repo = CedarDeploymentRepository(session)
        active_deployment = await deploy_repo.get_latest_for_org(org_id)
        bundle_snapshot = active_deployment.bundle_snapshot if active_deployment else None
        active_hash = active_deployment.bundle_hash if active_deployment else None

        registered_aliases = extract_registered_aliases(bundle_snapshot)
        forbidden_actions = extract_forbidden_actions(bundle_snapshot)

        # ── 4. Run detectors ──────────────────────────────────────────────────
        inp = AnalysisInput(
            log_entries=entries,
            active_bundle_hash=active_hash,
            registered_alias_ids=registered_aliases,
            forbidden_actions=forbidden_actions,
            baseline_call_rate=scan_state.baseline_call_rate if scan_state else None,
            anomaly_threshold=settings.cloudwatch_volume_anomaly_threshold,
            org_id=org_id,
            project_id=project_id,
            environment=environment,
        )
        detected = analyse(inp)

        logger.info(
            "CloudWatchScanWorker: %d anomalies detected org=%s",
            len(detected),
            org_id,
        )

        # ── 5. Ingest findings ────────────────────────────────────────────────
        batch_id = f"cwd_{job_id}"
        finding_repo = FindingRepository(session)
        accepted = 0
        quarantined = 0

        for finding in detected:
            try:
                await finding_repo.create(
                    finding_id=generate_id("find_"),
                    project_id=project_id,
                    environment=environment,
                    category="governance",
                    severity=finding.severity,
                    title=finding.title,
                    source={
                        "tool_name": "pearl-cloudwatch-bridge",
                        "tool_type": "cloudwatch",
                        "trust_label": "trusted_internal",
                    },
                    full_data={
                        "anomaly_code": finding.anomaly_code,
                        **finding.details,
                    },
                    normalized=True,
                    detected_at=now,
                    batch_id=batch_id,
                    anomaly_code=finding.anomaly_code,
                    status="open",
                )
                accepted += 1
            except Exception as exc:
                logger.warning(
                    "CloudWatchScanWorker: failed to persist finding %s: %s",
                    finding.anomaly_code,
                    exc,
                )
                quarantined += 1

        if accepted + quarantined > 0:
            batch_repo = FindingBatchRepository(session)
            await batch_repo.create(
                batch_id=batch_id,
                source_system="cloudwatch_scan",
                trust_label="trusted_internal",
                accepted_count=accepted,
                quarantined_count=quarantined,
                normalized_count=accepted,
            )
            await session.flush()

        # ── 6. Update watermark and baseline metrics ──────────────────────────
        new_watermark = watermark_from_entries(entries) or end_time
        # Update rolling baseline call rate (simple EMA with α = 0.2)
        observed_rate = float(len(entries))
        current_baseline = scan_state.baseline_call_rate if scan_state else None
        if current_baseline is None:
            new_baseline = observed_rate
        else:
            new_baseline = 0.8 * current_baseline + 0.2 * observed_rate

        await state_repo.upsert(
            org_id=org_id,
            log_watermark=new_watermark,
            last_scan_job_id=job_id,
            last_scan_findings_count=accepted,
            last_scan_entries_processed=len(entries),
            baseline_call_rate=new_baseline,
        )
        await session.flush()

        return {
            "result_refs": [{
                "ref_id": batch_id,
                "kind": "scan_batch",
                "summary": (
                    f"CloudWatch scan: {len(entries)} entries, "
                    f"{accepted} findings"
                ),
                "entries_processed": len(entries),
                "findings_accepted": accepted,
                "findings_quarantined": quarantined,
                "watermark": new_watermark.isoformat(),
                "anomalies": [f.anomaly_code for f in detected],
            }]
        }
