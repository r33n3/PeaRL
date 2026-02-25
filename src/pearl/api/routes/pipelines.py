"""Promotion pipeline CRUD routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import ConflictError, NotFoundError, ValidationError
from pearl.repositories.pipeline_repo import PromotionPipelineRepository
from pearl.repositories.promotion_repo import PromotionGateRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Pipelines"])


def _serialize_pipeline(p) -> dict:
    return {
        "pipeline_id": p.pipeline_id,
        "project_id": p.project_id,
        "name": p.name,
        "description": p.description,
        "stages": p.stages if isinstance(p.stages, list) else [],
        "is_default": p.is_default,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@router.get("/pipelines", status_code=200)
async def list_pipelines(db: AsyncSession = Depends(get_db)) -> list[dict]:
    repo = PromotionPipelineRepository(db)
    pipelines = await repo.list_all()
    return [_serialize_pipeline(p) for p in pipelines]


@router.get("/pipelines/default", status_code=200)
async def get_default_pipeline(db: AsyncSession = Depends(get_db)) -> dict:
    repo = PromotionPipelineRepository(db)
    pipeline = await repo.get_default()
    if not pipeline:
        raise NotFoundError("Default pipeline", "default")
    return _serialize_pipeline(pipeline)


@router.get("/pipelines/{pipeline_id}", status_code=200)
async def get_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = PromotionPipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline:
        raise NotFoundError("Promotion pipeline", pipeline_id)
    return _serialize_pipeline(pipeline)


@router.post("/pipelines", status_code=201)
async def create_pipeline(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    stages = body.get("stages", [])
    if not stages:
        raise ValidationError("stages must contain at least one entry")

    repo = PromotionPipelineRepository(db)
    pipeline_id = body.get("pipeline_id", generate_id("pipe_"))
    pipeline = await repo.create(
        pipeline_id=pipeline_id,
        name=body["name"],
        description=body.get("description"),
        stages=stages,
        is_default=body.get("is_default", False),
        project_id=body.get("project_id"),
    )
    await db.commit()
    return _serialize_pipeline(pipeline)


@router.put("/pipelines/{pipeline_id}", status_code=200)
async def update_pipeline(
    pipeline_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = PromotionPipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline:
        raise NotFoundError("Promotion pipeline", pipeline_id)

    old_stages = pipeline.stages if isinstance(pipeline.stages, list) else []
    new_stages = body.get("stages", old_stages)

    update_kwargs: dict = {}
    if "name" in body:
        update_kwargs["name"] = body["name"]
    if "description" in body:
        update_kwargs["description"] = body.get("description")
    if "stages" in body:
        update_kwargs["stages"] = new_stages

    if update_kwargs:
        await repo.update(pipeline, **update_kwargs)

    # Auto-create empty gates for new adjacent stage transitions
    if "stages" in body:
        await _ensure_gates_for_stages(new_stages, db)

    await db.commit()
    return _serialize_pipeline(pipeline)


@router.delete("/pipelines/{pipeline_id}", status_code=204)
async def delete_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = PromotionPipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline:
        raise NotFoundError("Promotion pipeline", pipeline_id)
    if pipeline.is_default:
        raise ConflictError("Cannot delete the active default pipeline")
    await repo.delete(pipeline_id)
    await db.commit()


@router.post("/pipelines/{pipeline_id}/set-default", status_code=200)
async def set_default_pipeline(
    pipeline_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = PromotionPipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline:
        raise NotFoundError("Promotion pipeline", pipeline_id)
    await repo.set_default(pipeline_id)
    await db.commit()
    return {"pipeline_id": pipeline_id, "is_default": True}


async def _ensure_gates_for_stages(stages: list, db: AsyncSession) -> None:
    """Auto-create empty gates for each adjacent pair in the stage list (idempotent)."""
    if len(stages) < 2:
        return
    sorted_stages = sorted(stages, key=lambda s: s.get("order", 0))
    gate_repo = PromotionGateRepository(db)
    for i in range(len(sorted_stages) - 1):
        src = sorted_stages[i]["key"]
        tgt = sorted_stages[i + 1]["key"]
        existing = await gate_repo.get_for_transition(src, tgt, project_id=None)
        if not existing:
            await gate_repo.create(
                gate_id=generate_id("gate_"),
                source_environment=src,
                target_environment=tgt,
                project_id=None,
                rules=[],
            )
