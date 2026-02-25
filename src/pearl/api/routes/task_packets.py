"""Task packet generation and execution bridge API routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import ConflictError, NotFoundError
from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.task_packet_generator import generate_task_packet

router = APIRouter(tags=["TaskPackets"])


class ClaimRequest(BaseModel):
    agent_id: str


class CompleteRequest(BaseModel):
    status: str  # "success" | "failed" | "partial"
    changes_summary: str = ""
    finding_ids_resolved: list[str] = []


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
                "findings_resolved": resolved_count,
                "agent_id": packet.agent_id,
            },
        )
        db.add(audit_row)
    except Exception:
        pass  # Telemetry is best-effort

    await db.commit()

    return {
        "packet_id": packet_id,
        "status": body.status,
        "findings_resolved": resolved_count,
        "completed_at": now.isoformat(),
    }
