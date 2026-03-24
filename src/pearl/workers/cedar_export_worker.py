"""Worker that generates a Cedar policy bundle and deploys it to AgentCore.

Triggered:
  - Automatically after an ``cedar_deployment`` or ``promotion_gate`` approval
    is approved (when ``settings.agentcore_deploy_on_approval`` is True).
  - Manually via POST /agentcore/deploy.
  - By the scheduler (future).

Payload fields:
    org_id (str):              Organisation whose governance state is exported.
    triggered_by (str):        'approval' | 'manual' | 'scheduler'
    approval_id (str|None):    Approval request that triggered this.
    deployed_by (str):         Subject identifier of the initiating actor.
    agent_aliases (list[dict]): Registered agent aliases to permit (optional).
    blocked_rules (list[str]): Gate rule types currently blocking (optional).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.integrations.agentcore.agentcore_client import AgentCoreClient
from pearl.integrations.agentcore.cedar_generator import CedarPolicyGenerator
from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository
from pearl.repositories.org_baseline_repo import OrgBaselineRepository
from pearl.services.id_generator import generate_id
from pearl.workers.base import BaseWorker

logger = logging.getLogger(__name__)


class CedarExportWorker(BaseWorker):
    """Generates and deploys a Cedar policy bundle to AWS AgentCore."""

    async def process(self, job_id: str, payload: dict, session: AsyncSession) -> dict:
        org_id: str = payload.get("org_id", "")
        triggered_by: str = payload.get("triggered_by", "manual")
        approval_id: str | None = payload.get("approval_id")
        deployed_by: str = payload.get("deployed_by", "system")
        agent_aliases: list[dict] = payload.get("agent_aliases") or []
        blocked_rules: list[str] = payload.get("blocked_rules") or []

        if not org_id:
            raise ValueError("payload must include org_id")

        gateway_arn: str = settings.agentcore_gateway_arn

        # ── 1. Load org baseline controls ─────────────────────────────────────
        baseline_controls: dict = {}
        try:
            baseline_repo = OrgBaselineRepository(session)
            baseline_row = await baseline_repo.get_org_wide()
            if baseline_row and baseline_row.baseline_doc:
                baseline_controls = baseline_row.baseline_doc.get("defaults") or {}
        except Exception as exc:
            logger.warning(
                "CedarExportWorker: could not load baseline org=%s: %s", org_id, exc
            )

        # ── 2. Generate Cedar bundle ───────────────────────────────────────────
        generator = CedarPolicyGenerator()
        bundle = generator.generate_bundle(
            org_id=org_id,
            gateway_arn=gateway_arn,
            agent_aliases=agent_aliases,
            blocked_rule_types=blocked_rules,
            baseline_controls=baseline_controls,
        )

        bundle_json = bundle.to_json_dict()
        bundle_hash = bundle.bundle_hash

        # ── 3. Skip deploy if bundle is unchanged ─────────────────────────────
        deploy_repo = CedarDeploymentRepository(session)
        existing = await deploy_repo.get_latest_for_org(org_id)
        if existing and existing.bundle_hash == bundle_hash:
            logger.info(
                "CedarExportWorker: bundle unchanged org=%s hash=%.12s — skip",
                org_id,
                bundle_hash,
            )
            return {
                "result_refs": [{
                    "ref_id": existing.deployment_id,
                    "kind": "cedar_deployment",
                    "summary": "Bundle unchanged — no deploy needed",
                    "bundle_hash": bundle_hash,
                    "status": "skipped",
                }]
            }

        # ── 4. Persist deployment record (pending) ────────────────────────────
        deployment_id = generate_id("cdep_")
        await deploy_repo.supersede_active(org_id)
        deployment_row = await deploy_repo.create(
            deployment_id=deployment_id,
            org_id=org_id,
            gateway_arn=gateway_arn or "dry-run",
            bundle_hash=bundle_hash,
            bundle_snapshot=bundle_json,
            status="pending",
            deployed_by=deployed_by,
            triggered_by=triggered_by,
            approval_id=approval_id,
            job_id=job_id,
        )
        await session.flush()

        # ── 5. Deploy to AgentCore ─────────────────────────────────────────────
        if settings.cedar_bundle_dry_run or not gateway_arn:
            agentcore_deployment_id = f"dryrun_{deployment_id}"
            logger.info(
                "CedarExportWorker: dry-run org=%s hash=%.12s", org_id, bundle_hash
            )
        else:
            try:
                client = AgentCoreClient(
                    gateway_arn=gateway_arn,
                    aws_region=settings.agentcore_aws_region,
                    aws_access_key_id=settings.agentcore_aws_access_key_id,
                    aws_secret_access_key=settings.agentcore_aws_secret_access_key,
                )
                agentcore_deployment_id = await client.deploy_policy_bundle(bundle_json)
            except Exception as exc:
                logger.error(
                    "CedarExportWorker: deploy failed org=%s: %s", org_id, exc
                )
                await deploy_repo.update(
                    deployment_row,
                    status="failed",
                    error_detail=str(exc),
                )
                await session.flush()
                raise

        # ── 6. Mark active ────────────────────────────────────────────────────
        await deploy_repo.update(
            deployment_row,
            status="active",
            agentcore_deployment_id=agentcore_deployment_id,
        )
        await session.flush()

        logger.info(
            "CedarExportWorker: complete org=%s hash=%.12s agentcore_id=%s policies=%d",
            org_id,
            bundle_hash,
            agentcore_deployment_id,
            len(bundle.policies),
        )

        return {
            "result_refs": [{
                "ref_id": deployment_id,
                "kind": "cedar_deployment",
                "summary": (
                    f"Cedar bundle deployed to AgentCore "
                    f"({len(bundle.policies)} policies)"
                ),
                "bundle_hash": bundle_hash,
                "agentcore_deployment_id": agentcore_deployment_id,
                "policy_count": len(bundle.policies),
                "status": "active",
            }]
        }
