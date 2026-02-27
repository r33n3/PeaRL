"""Agent integration endpoints — brief, task list, and gate status for coding agents."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.promotion_repo import PromotionEvaluationRepository
from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.promotion.gate_evaluator import next_environment
from pearl.services.promotion.requirement_resolver import resolve_requirements

router = APIRouter(tags=["Agent"])


@router.get("/projects/{project_id}/promotions/agent-brief")
async def get_agent_brief(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return a structured brief for a coding agent: current gate status, open task packets, requirements."""
    proj_repo = ProjectRepository(db)
    project = await proj_repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    # Current stage
    env_repo = EnvironmentProfileRepository(db)
    env_profile = await env_repo.get_by_project(project_id)
    current_stage = env_profile.environment if env_profile else "sandbox"

    # Next stage
    next_stage = await next_environment(current_stage, db)

    # Latest gate evaluation
    eval_repo = PromotionEvaluationRepository(db)
    latest_eval = await eval_repo.get_latest_by_project(project_id)

    gate_status = "not_evaluated"
    ready_to_elevate = False
    last_evaluated_at = None
    blockers_count = 0
    requirement_statuses = []

    if latest_eval:
        gate_status = latest_eval.status
        ready_to_elevate = (latest_eval.status == "passed")
        last_evaluated_at = latest_eval.evaluated_at.isoformat() if latest_eval.evaluated_at else None
        blockers_count = latest_eval.failed_count or 0

        # Build requirement status from rule_results
        rule_results = latest_eval.rule_results or []
        for rr in rule_results:
            rr_dict = rr if isinstance(rr, dict) else (rr.model_dump() if hasattr(rr, "model_dump") else {})
            params = rr_dict.get("details") or {}
            control_id = params.get("control") or rr_dict.get("rule_type", "")
            status = "satisfied" if rr_dict.get("result") == "pass" else (
                "skipped" if rr_dict.get("result") in ("skip", "exception") else "missing"
            )
            requirement_statuses.append({
                "control_id": control_id,
                "rule_type": rr_dict.get("rule_type"),
                "status": status,
                "action": rr_dict.get("message") if status == "missing" else None,
                "evidence_ref": None,
            })

    # Open task packets
    tp_repo = TaskPacketRepository(db)
    all_packets = await tp_repo.list_by_project(project_id)
    open_packets = [
        p for p in all_packets
        if (p.packet_data or {}).get("status") in ("pending", "in_progress")
        and p.completed_at is None
    ]

    open_task_packets = [
        {
            "task_packet_id": p.task_packet_id,
            "rule_id": (p.packet_data or {}).get("rule_id"),
            "rule_type": (p.packet_data or {}).get("rule_type"),
            "fix_guidance": (p.packet_data or {}).get("fix_guidance"),
            "status": (p.packet_data or {}).get("status"),
            "transition": (p.packet_data or {}).get("transition"),
            "finding_ids": (p.packet_data or {}).get("finding_ids", []),
            "claimed_at": p.claimed_at.isoformat() if p.claimed_at else None,
            "agent_id": p.agent_id,
        }
        for p in open_packets
        if (p.packet_data or {}).get("task_type") == "remediate_gate_blocker"
    ]

    # Resolved requirements (BU-derived)
    resolved_reqs = []
    if next_stage:
        try:
            resolved_reqs = await resolve_requirements(
                project_id=project_id,
                source_env=current_stage,
                target_env=next_stage,
                session=db,
            )
        except Exception:
            pass

    return {
        "project_id": project_id,
        "current_stage": current_stage,
        "next_stage": next_stage,
        "gate_status": gate_status,
        "ready_to_elevate": ready_to_elevate,
        "requirements": requirement_statuses,
        "resolved_requirements": [r.model_dump() for r in resolved_reqs],
        "open_task_packets": open_task_packets,
        "blockers_count": blockers_count,
        "last_evaluated_at": last_evaluated_at,
    }
