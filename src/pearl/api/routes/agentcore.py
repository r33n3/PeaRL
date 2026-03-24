"""AgentCore integration routes — Cedar policy deployment and drift status."""

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import RequireAdmin, RequireOperator, get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.cedar_deployment_repo import CedarDeploymentRepository
from pearl.repositories.agentcore_scan_state_repo import AgentCoreScanStateRepository
from pearl.workers.queue import enqueue_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agentcore", tags=["AgentCore"])


@router.get("/deployments")
async def list_cedar_deployments(
    org_id: str,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    _user: dict = RequireOperator,
) -> list[dict]:
    """Return Cedar policy deployment history for an org, newest first."""
    repo = CedarDeploymentRepository(db)
    rows = await repo.list_for_org(org_id, limit=limit)
    return [_serialize_deployment(r) for r in rows]


@router.get("/deployments/latest")
async def get_latest_cedar_deployment(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = RequireOperator,
) -> dict:
    """Return the currently active Cedar deployment for an org."""
    repo = CedarDeploymentRepository(db)
    row = await repo.get_latest_for_org(org_id)
    if not row:
        raise NotFoundError("CedarDeployment", org_id)
    return _serialize_deployment(row)


@router.get("/scan-state")
async def get_agentcore_scan_state(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = RequireOperator,
) -> dict:
    """Return the CloudWatch scan state (watermark, baseline metrics) for an org."""
    repo = AgentCoreScanStateRepository(db)
    row = await repo.get_for_org(org_id)
    if not row:
        raise NotFoundError("AgentCoreScanState", org_id)
    return {
        "state_id": row.state_id,
        "org_id": row.org_id,
        "log_watermark": row.log_watermark.isoformat() if row.log_watermark else None,
        "last_scan_job_id": row.last_scan_job_id,
        "last_scan_findings_count": row.last_scan_findings_count,
        "last_scan_entries_processed": row.last_scan_entries_processed,
        "baseline_call_rate": row.baseline_call_rate,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.post("/deploy", status_code=202)
async def trigger_cedar_deploy(
    body: dict,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _admin: dict = RequireAdmin,
) -> dict:
    """Manually trigger a Cedar policy export and deployment to AgentCore.

    Request body:
        org_id (str):              Organisation to export.
        agent_aliases (list[dict]): Optional registered alias list.
        blocked_rules (list[str]): Optional blocking gate rule types.
    """
    org_id: str = body.get("org_id", "")
    if not org_id:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError("org_id is required")

    current_user: dict = getattr(request.state, "user", {})
    deployed_by: str = current_user.get("sub", "system")
    redis = getattr(request.app.state, "redis", None)

    job = await enqueue_job(
        session=db,
        job_type="export_cedar_policies",
        project_id=None,
        trace_id=getattr(request.state, "trace_id", ""),
        payload={
            "org_id": org_id,
            "triggered_by": "manual",
            "deployed_by": deployed_by,
            "agent_aliases": body.get("agent_aliases") or [],
            "blocked_rules": body.get("blocked_rules") or [],
        },
        redis=redis,
    )
    await db.commit()

    return {"job_id": job.job_id, "status": "queued"}


# ── helpers ────────────────────────────────────────────────────────────────────

def _serialize_deployment(row) -> dict:
    return {
        "deployment_id": row.deployment_id,
        "org_id": row.org_id,
        "gateway_arn": row.gateway_arn,
        "bundle_hash": row.bundle_hash,
        "status": row.status,
        "deployed_by": row.deployed_by,
        "triggered_by": row.triggered_by,
        "approval_id": row.approval_id,
        "job_id": row.job_id,
        "agentcore_deployment_id": row.agentcore_deployment_id,
        "error_detail": row.error_detail,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
