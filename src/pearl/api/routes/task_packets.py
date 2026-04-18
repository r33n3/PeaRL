"""Task packet generation and execution bridge API routes."""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import ConflictError, NotFoundError, ValidationError
from pearl.repositories.promotion_repo import PromotionGateRepository
from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.task_packet_generator import generate_task_packet

logger = logging.getLogger(__name__)

router = APIRouter(tags=["TaskPackets"])

# Valid execution phases
VALID_PHASES = {"planning", "coding", "testing", "review", "complete", "failed"}
TERMINAL_PHASES = {"complete", "failed"}

# Legal forward transitions
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "planning": {"coding", "failed"},
    "coding": {"testing", "failed"},
    "testing": {"review", "failed"},
    "review": {"complete", "failed"},
    "complete": set(),
    "failed": set(),
}


class ClaimRequest(BaseModel):
    agent_id: str


class CompleteRequest(BaseModel):
    status: str  # "completed" | "failed" | "partial"
    changes_summary: str = ""
    finding_ids_resolved: list[str] = []
    fix_summary: str = ""
    commit_ref: str = ""
    files_changed: list[str] = []
    evidence_notes: str = ""


class PhaseTransitionRequest(BaseModel):
    phase: str
    agent_id: Optional[str] = None


@router.post("/projects/{project_id}/task-packets", status_code=201)
async def generate_task_packet_endpoint(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    body = await request.json()

    packet = await generate_task_packet(
        project_id=project_id,
        task_type=body["task_type"],
        task_summary=body["task_summary"],
        environment=body["environment"],
        trace_id=body.get("trace_id", trace_id),
        affected_components=body.get("affected_components"),
        change_hints=body.get("change_hints"),
        context_budget=body.get("context_budget"),
        session=db,
    )

    # Store the task packet
    repo = TaskPacketRepository(db)
    packet_data = packet.model_dump(mode="json", exclude_none=True)
    await repo.create(
        task_packet_id=packet.task_packet_id,
        project_id=project_id,
        environment=packet.environment,
        packet_data=packet_data,
        trace_id=packet.trace_id,
    )
    await db.commit()

    return packet_data


@router.get("/task-packets/{packet_id}", status_code=200)
async def get_task_packet(
    packet_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Retrieve a task packet by ID, including execution phase and phase history."""
    repo = TaskPacketRepository(db)
    packet = await repo.get(packet_id)
    if not packet:
        raise NotFoundError("TaskPacket", packet_id)

    return {
        "task_packet_id": packet.task_packet_id,
        "project_id": packet.project_id,
        "environment": packet.environment,
        "trace_id": packet.trace_id,
        "schema_version": packet.schema_version,
        "agent_id": packet.agent_id,
        "claimed_at": packet.claimed_at.isoformat() if packet.claimed_at else None,
        "completed_at": packet.completed_at.isoformat() if packet.completed_at else None,
        "outcome": packet.outcome,
        "execution_phase": packet.execution_phase,
        "phase_history": packet.phase_history,
        "packet_data": packet.packet_data,
    }


@router.patch("/task-packets/{packet_id}/phase", status_code=200)
async def update_task_packet_phase(
    packet_id: str,
    body: PhaseTransitionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Transition execution phase of a task packet."""
    repo = TaskPacketRepository(db)
    packet = await repo.get(packet_id)
    if not packet:
        raise NotFoundError("TaskPacket", packet_id)

    new_phase = body.phase
    if new_phase not in VALID_PHASES:
        raise HTTPException(status_code=422, detail=f"Invalid phase '{new_phase}'. Must be one of: {', '.join(sorted(VALID_PHASES))}")

    current_phase = packet.execution_phase
    allowed_next = LEGAL_TRANSITIONS.get(current_phase, set())

    if current_phase in TERMINAL_PHASES:
        raise HTTPException(
            status_code=422,
            detail=f"Cannot transition from terminal phase '{current_phase}'. Phases 'complete' and 'failed' have no further transitions."
        )

    if new_phase not in allowed_next:
        raise HTTPException(
            status_code=422,
            detail=f"Illegal phase transition from '{current_phase}' to '{new_phase}'. Allowed transitions from '{current_phase}': {', '.join(sorted(allowed_next)) or 'none'}"
        )

    # Determine agent_id
    agent_id = body.agent_id
    if not agent_id:
        user = getattr(request.state, "user", None) or {}
        agent_id = user.get("sub", "unknown")

    now = datetime.now(timezone.utc)
    history_entry = {
        "phase": new_phase,
        "timestamp": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent_id": agent_id,
    }

    # Read list, append in Python, write back
    current_history = list(packet.phase_history or [])
    current_history.append(history_entry)

    packet.execution_phase = new_phase
    packet.phase_history = current_history

    await db.commit()

    return {
        "task_packet_id": packet_id,
        "project_id": packet.project_id,
        "environment": packet.environment,
        "trace_id": packet.trace_id,
        "schema_version": packet.schema_version,
        "agent_id": packet.agent_id,
        "claimed_at": packet.claimed_at.isoformat() if packet.claimed_at else None,
        "completed_at": packet.completed_at.isoformat() if packet.completed_at else None,
        "outcome": packet.outcome,
        "execution_phase": packet.execution_phase,
        "phase_history": packet.phase_history,
        "packet_data": packet.packet_data,
    }


@router.post("/task-packets/{packet_id}/claim", status_code=200)
async def claim_task_packet(
    packet_id: str,
    body: ClaimRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Agent claims a task packet for execution."""
    repo = TaskPacketRepository(db)
    packet = await repo.get(packet_id)
    if not packet:
        raise NotFoundError("TaskPacket", packet_id)

    if packet.agent_id and packet.claimed_at and not packet.completed_at:
        raise ConflictError(f"TaskPacket '{packet_id}' is already claimed by agent '{packet.agent_id}'")

    now = datetime.now(timezone.utc)
    packet.agent_id = body.agent_id
    packet.claimed_at = now
    packet.completed_at = None
    packet.outcome = None

    # Snapshot allowance profile version at claim time
    if packet.allowance_profile_id:
        from pearl.repositories.allowance_profile_repo import AllowanceProfileRepository
        ap_repo = AllowanceProfileRepository(db)
        ap_row = await ap_repo.get(packet.allowance_profile_id)
        if ap_row:
            packet.allowance_profile_version = ap_row.profile_version

    # Update status in packet_data
    data = dict(packet.packet_data)
    data["status"] = "in_progress"
    data["agent_id"] = body.agent_id
    data["claimed_at"] = now.isoformat()
    packet.packet_data = data

    await db.commit()
    return {"packet_id": packet_id, "agent_id": body.agent_id, "status": "in_progress"}


@router.post("/task-packets/{packet_id}/complete", status_code=200)
async def complete_task_packet(
    packet_id: str,
    body: CompleteRequest,
    background_tasks: BackgroundTasks,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Agent reports the outcome of a task packet execution."""
    from pearl.db.models.finding import FindingRow
    from sqlalchemy import select

    repo = TaskPacketRepository(db)
    packet = await repo.get(packet_id)
    if not packet:
        raise NotFoundError("TaskPacket", packet_id)

    now = datetime.now(timezone.utc)
    packet.completed_at = now
    packet.outcome = {
        "status": body.status,
        "changes_summary": body.changes_summary,
        "fix_summary": body.fix_summary,
        "commit_ref": body.commit_ref,
        "files_changed": body.files_changed,
        "evidence_notes": body.evidence_notes,
        "finding_ids_resolved": body.finding_ids_resolved,
        "completed_at": now.isoformat(),
    }

    # Update packet_data status
    data = dict(packet.packet_data)
    data["status"] = body.status
    data["completed_at"] = now.isoformat()
    packet.packet_data = data

    # Mark resolved findings
    resolved_count = 0
    if body.finding_ids_resolved:
        stmt = select(FindingRow).where(FindingRow.finding_id.in_(body.finding_ids_resolved))
        result = await db.execute(stmt)
        findings = list(result.scalars().all())
        for f in findings:
            f.status = "resolved"
            resolved_count += 1

    # Create governance telemetry audit event
    try:
        from pearl.db.models.governance_telemetry import ClientAuditEventRow
        from pearl.services.id_generator import generate_id

        audit_row = ClientAuditEventRow(
            event_id=generate_id("evt_"),
            event_type="task_packet_completed",
            project_id=packet.project_id,
            timestamp=now,
            action="task_packet_complete",
            decision=body.status,
            tool_name="agent",
            details={
                "packet_id": packet_id,
                "outcome_status": body.status,
                "fix_summary": body.fix_summary,
                "commit_ref": body.commit_ref,
                "findings_resolved": resolved_count,
                "agent_id": packet.agent_id,
            },
        )
        db.add(audit_row)
    except Exception:
        logger.warning("Audit event creation failed for packet %s", packet_id, exc_info=True)

    await db.commit()

    # Re-evaluate gate after completion
    gate_status = None
    gate_evaluation_id = None

    # Compute transition envs before the try block so gate lookup can use them
    _transition = (packet.packet_data or {}).get("transition", "")
    _source_env = packet.environment
    _target_env: str | None = None
    if "->" in _transition:
        _parts = _transition.split("->")
        _source_env = _parts[0].strip()
        _target_env = _parts[1].strip()

    # Look up gate mode: manual gates (auto_pass=False) must surface re-eval failures
    _gate_repo = PromotionGateRepository(db)
    _gate = await _gate_repo.get_for_transition(_source_env, _target_env or "", packet.project_id)
    # If no gate is configured, default to auto-elevation (best-effort) mode.
    # Only an explicitly configured gate with auto_pass=False is treated as manual.
    _gate_is_manual = (_gate is not None) and (not _gate.auto_pass)

    try:
        from pearl.services.promotion.gate_evaluator import evaluate_promotion
        from pearl.api.routes.stream import publish_event

        evaluation = await evaluate_promotion(
            project_id=packet.project_id,
            source_environment=_source_env,
            target_environment=_target_env,
            session=db,
        )
        await db.commit()
        gate_status = evaluation.status.value if hasattr(evaluation.status, "value") else str(evaluation.status)
        gate_evaluation_id = evaluation.evaluation_id

        # Publish SSE event
        if request:
            redis = getattr(request.app.state, "redis", None)
            await publish_event(redis, "gate_updated", {
                "project_id": packet.project_id,
                "evaluation_id": evaluation.evaluation_id,
                "gate_status": gate_status,
                "triggered_by": "task_packet_complete",
                "packet_id": packet_id,
            })

        # Auto-elevation if gate passes and transition doesn't require approval
        if evaluation.status.value == "passed" if hasattr(evaluation.status, "value") else evaluation.status == "passed":
            await _check_auto_elevation(
                project_id=packet.project_id,
                source_env=_source_env,
                target_env=_target_env or "",
                session=db,
                request=request,
            )
            await db.commit()
    except Exception:
        if _gate_is_manual:
            raise
        logger.warning(
            "Gate re-evaluation failed (auto-elevation mode, project=%s, %s->%s)",
            packet.project_id, _source_env, _target_env,
            exc_info=True,
        )

    # AGP-05: detect missing context receipt (background — post-response)
    session_factory = getattr(getattr(request, "app", None), "state", None)
    session_factory = getattr(session_factory, "db_session_factory", None) if session_factory else None
    user_sub = "unknown"
    if request and hasattr(request, "state") and hasattr(request.state, "user"):
        user_sub = (request.state.user or {}).get("sub", "unknown")
    if session_factory:
        async def _agp05(sf=session_factory, pid=packet.project_id, at=now, sub=user_sub, tid=packet.trace_id):
            from pearl.security.anomaly_detector import detect_agp05_missing_receipt, emit_detection
            async with sf() as s:
                result = await detect_agp05_missing_receipt(s, pid, at, sub, tid)
                if result:
                    emit_detection(result)
        background_tasks.add_task(_agp05)

    return {
        "packet_id": packet_id,
        "status": body.status,
        "findings_resolved": resolved_count,
        "completed_at": now.isoformat(),
        "gate_status": gate_status,
        "gate_evaluation_id": gate_evaluation_id,
    }


async def _check_auto_elevation(
    project_id: str,
    source_env: str,
    target_env: str,
    session,
    request=None,
) -> None:
    """Auto-elevate if org env config says requires_approval=false for this transition."""
    try:
        from pearl.repositories.org_env_config_repo import OrgEnvironmentConfigRepository
        from pearl.repositories.promotion_repo import PromotionHistoryRepository
        from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
        from pearl.repositories.project_repo import ProjectRepository
        from pearl.services.id_generator import generate_id
        from datetime import datetime, timezone

        proj_repo = ProjectRepository(session)
        project = await proj_repo.get(project_id)
        if not project or not project.org_id:
            return

        config_repo = OrgEnvironmentConfigRepository(session)
        config = await config_repo.get_by_org(project.org_id)
        if not config:
            return

        # Find the stage config for target_env
        stage_config = None
        for stage in (config.stages or []):
            if stage.get("name") == target_env:
                stage_config = stage
                break

        if not stage_config:
            return

        if stage_config.get("requires_approval", True):
            return  # Needs human approval — skip auto-elevation

        # Auto-elevate: create PromotionHistoryRow + update environment profile
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)

        history_repo = PromotionHistoryRepository(session)
        await history_repo.create(
            history_id=generate_id("hist_"),
            project_id=project_id,
            source_environment=source_env,
            target_environment=target_env,
            evaluation_id="auto_elevation",
            promoted_by="pearl_auto",
            promoted_at=now,
            details={"auto_elevated": True, "reason": "gate_passed_no_approval_required"},
        )

        env_repo = EnvironmentProfileRepository(session)
        env_profile = await env_repo.get_by_project(project_id)
        if env_profile:
            env_profile.environment = target_env

    except Exception:
        logger.warning(
            "Auto-elevation failed (project=%s, %s->%s)",
            project_id, source_env, target_env,
            exc_info=True,
        )
