"""Task packet generation API route."""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.repositories.task_packet_repo import TaskPacketRepository
from pearl.services.task_packet_generator import generate_task_packet

router = APIRouter(tags=["TaskPackets"])


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
