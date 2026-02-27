"""Business Unit API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import ConflictError, NotFoundError
from pearl.repositories.business_unit_repo import BusinessUnitRepository
from pearl.repositories.framework_requirement_repo import FrameworkRequirementRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["BusinessUnits"])


@router.get("/business-units")
async def list_business_units(
    org_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = BusinessUnitRepository(db)
    if org_id:
        bus = await repo.get_by_org(org_id)
    else:
        from sqlalchemy import select
        from pearl.db.models.business_unit import BusinessUnitRow
        result = await db.execute(select(BusinessUnitRow))
        bus = list(result.scalars().all())
    return [_bu_dict(bu) for bu in bus]


@router.post("/business-units", status_code=201)
async def create_business_unit(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    org_id = body.get("org_id")
    name = body.get("name")
    if not org_id or not name:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError("org_id and name are required")

    repo = BusinessUnitRepository(db)
    existing = await repo.get_by_name(org_id, name)
    if existing:
        raise ConflictError(f"Business unit '{name}' already exists in org '{org_id}'")

    bu_id = body.get("bu_id") or generate_id("bu_")
    bu = await repo.create(
        bu_id=bu_id,
        org_id=org_id,
        name=name,
        description=body.get("description"),
        framework_selections=body.get("framework_selections", []),
        additional_guardrails=body.get("additional_guardrails", {}),
    )
    await db.commit()
    return _bu_dict(bu)


@router.get("/business-units/{bu_id}")
async def get_business_unit(
    bu_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = BusinessUnitRepository(db)
    bu = await repo.get(bu_id)
    if not bu:
        raise NotFoundError("BusinessUnit", bu_id)
    return _bu_dict(bu)


@router.patch("/business-units/{bu_id}")
async def update_business_unit(
    bu_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = BusinessUnitRepository(db)
    bu = await repo.get(bu_id)
    if not bu:
        raise NotFoundError("BusinessUnit", bu_id)

    update_fields = {}
    for field in ("name", "description", "additional_guardrails"):
        if field in body:
            update_fields[field] = body[field]
    await repo.update(bu, **update_fields)
    await db.commit()
    return _bu_dict(bu)


@router.delete("/business-units/{bu_id}", status_code=204)
async def delete_business_unit(
    bu_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = BusinessUnitRepository(db)
    bu = await repo.get(bu_id)
    if not bu:
        raise NotFoundError("BusinessUnit", bu_id)
    await repo.delete(bu_id)
    await db.commit()


@router.post("/business-units/{bu_id}/frameworks", status_code=201)
async def derive_framework_requirements(
    bu_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Derive FrameworkRequirementRows from framework selections."""
    bu_repo = BusinessUnitRepository(db)
    bu = await bu_repo.get(bu_id)
    if not bu:
        raise NotFoundError("BusinessUnit", bu_id)

    framework_selections = body.get("framework_selections") or bu.framework_selections or []

    # Update BU framework selections
    bu.framework_selections = framework_selections

    # Import catalogue and derive requirements
    from pearl.services.promotion.framework_catalogue import FRAMEWORK_CATALOGUE
    from pearl.repositories.framework_requirement_repo import FrameworkRequirementRepository

    req_repo = FrameworkRequirementRepository(db)
    # Delete existing requirements (idempotent)
    await req_repo.delete_by_bu(bu_id)

    created = 0
    for framework_key in framework_selections:
        controls = FRAMEWORK_CATALOGUE.get(framework_key, [])
        for control in controls:
            req_id = generate_id("freq_")
            await req_repo.create(
                requirement_id=req_id,
                bu_id=bu_id,
                framework=framework_key,
                control_id=control["control_id"],
                applies_to_transitions=control["applies_to_transitions"],
                requirement_level=control["requirement_level"],
                evidence_type=control["evidence_type"],
            )
            created += 1

    await db.commit()
    return {"bu_id": bu_id, "frameworks": framework_selections, "requirements_created": created}


@router.get("/business-units/{bu_id}/requirements")
async def list_bu_requirements(
    bu_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = BusinessUnitRepository(db)
    bu = await repo.get(bu_id)
    if not bu:
        raise NotFoundError("BusinessUnit", bu_id)

    req_repo = FrameworkRequirementRepository(db)
    reqs = await req_repo.get_by_bu(bu_id)
    return [
        {
            "requirement_id": r.requirement_id,
            "bu_id": r.bu_id,
            "framework": r.framework,
            "control_id": r.control_id,
            "applies_to_transitions": r.applies_to_transitions,
            "requirement_level": r.requirement_level,
            "evidence_type": r.evidence_type,
        }
        for r in reqs
    ]


def _bu_dict(bu) -> dict:
    return {
        "bu_id": bu.bu_id,
        "org_id": bu.org_id,
        "name": bu.name,
        "description": bu.description,
        "framework_selections": bu.framework_selections or [],
        "additional_guardrails": bu.additional_guardrails or {},
        "created_at": bu.created_at.isoformat() if bu.created_at else None,
        "updated_at": bu.updated_at.isoformat() if bu.updated_at else None,
    }
