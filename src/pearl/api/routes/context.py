"""Context engineering routes — contracts, packs, receipts."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.repositories.fairness_repo import (
    ContextContractRepository,
    ContextPackRepository,
    ContextReceiptRepository,
)
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Context Engineering"])


@router.post("/context/contracts", status_code=201)
async def create_context_contract(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ContextContractRepository(db)
    cc_id = body.get("cc_id", generate_id("cc_"))
    await repo.create(
        cc_id=cc_id,
        project_id=body.get("project_id"),
        required_artifacts=body.get("required_artifacts", []),
        gate_mode_per_env=body.get("gate_mode_per_env"),
        description=body.get("description"),
    )
    await db.commit()
    return {"cc_id": cc_id, "status": "created"}


@router.get("/context/contracts/{cc_id}", status_code=200)
async def get_context_contract(
    cc_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ContextContractRepository(db)
    cc = await repo.get(cc_id)
    if not cc:
        return {"error": "Context contract not found"}
    return {
        "cc_id": cc.cc_id,
        "project_id": cc.project_id,
        "required_artifacts": cc.required_artifacts,
        "gate_mode_per_env": cc.gate_mode_per_env,
        "description": cc.description,
    }


@router.post("/context/packs", status_code=201)
async def create_context_pack(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ContextPackRepository(db)
    cp_id = body.get("cp_id", generate_id("cp_"))
    await repo.create(
        cp_id=cp_id,
        project_id=body["project_id"],
        environment=body.get("environment", "dev"),
        pack_data=body.get("pack_data", {}),
        artifact_hashes=body.get("artifact_hashes"),
    )
    await db.commit()
    return {"cp_id": cp_id, "status": "created"}


@router.get("/context/packs/{cp_id}", status_code=200)
async def get_context_pack(
    cp_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ContextPackRepository(db)
    cp = await repo.get(cp_id)
    if not cp:
        return {"error": "Context pack not found"}
    return {
        "cp_id": cp.cp_id,
        "project_id": cp.project_id,
        "environment": cp.environment,
        "pack_data": cp.pack_data,
        "artifact_hashes": cp.artifact_hashes,
    }


@router.post("/context/receipts", status_code=201)
async def create_context_receipt(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ContextReceiptRepository(db)
    cr_id = body.get("cr_id", generate_id("cr_"))
    await repo.create(
        cr_id=cr_id,
        project_id=body["project_id"],
        commit_hash=body.get("commit_hash"),
        agent_id=body.get("agent_id"),
        tool_calls=body.get("tool_calls"),
        artifact_hashes=body.get("artifact_hashes"),
        consumed_at=datetime.now(timezone.utc),
    )
    await db.commit()
    return {"cr_id": cr_id, "status": "created"}


@router.get("/context/receipts", status_code=200)
async def list_context_receipts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = ContextReceiptRepository(db)
    receipts = await repo.list_by_field("project_id", project_id)
    return [
        {
            "cr_id": r.cr_id,
            "project_id": r.project_id,
            "commit_hash": r.commit_hash,
            "agent_id": r.agent_id,
            "consumed_at": r.consumed_at.isoformat() if r.consumed_at else None,
        }
        for r in receipts
    ]
