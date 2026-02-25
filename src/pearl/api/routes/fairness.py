"""Fairness governance routes — cases, requirements, evidence, signals."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.repositories.fairness_repo import (
    EvidencePackageRepository,
    FairnessCaseRepository,
    FairnessExceptionRepository,
    FairnessRequirementsSpecRepository,
    MonitoringSignalRepository,
)
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Fairness"])


# ─── Fairness Cases ──────────────────────────────

@router.post("/projects/{project_id}/fairness-cases", status_code=201)
async def create_fairness_case(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = FairnessCaseRepository(db)
    fc_id = body.get("fc_id", generate_id("fc_"))
    await repo.create(
        fc_id=fc_id,
        project_id=project_id,
        risk_tier=body.get("risk_tier", "r1"),
        fairness_criticality=body.get("fairness_criticality", "medium"),
        case_data=body.get("case_data"),
    )
    await db.commit()
    return {"fc_id": fc_id, "project_id": project_id, "status": "created"}


@router.get("/projects/{project_id}/fairness-cases", status_code=200)
async def list_fairness_cases(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = FairnessCaseRepository(db)
    cases = await repo.list_by_project(project_id)
    return [
        {
            "fc_id": c.fc_id,
            "risk_tier": c.risk_tier,
            "fairness_criticality": c.fairness_criticality,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in cases
    ]


# ─── Fairness Requirements ──────────────────────

@router.post("/projects/{project_id}/fairness-requirements", status_code=201)
async def create_fairness_requirements(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = FairnessRequirementsSpecRepository(db)
    frs_id = body.get("frs_id", generate_id("frs_"))
    await repo.create(
        frs_id=frs_id,
        project_id=project_id,
        requirements=body.get("requirements", []),
        version=body.get("version"),
    )
    await db.commit()
    return {"frs_id": frs_id, "project_id": project_id, "status": "created"}


@router.get("/projects/{project_id}/fairness-requirements", status_code=200)
async def get_fairness_requirements(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = FairnessRequirementsSpecRepository(db)
    frs = await repo.get_by_project(project_id)
    if not frs:
        return {"status": "not_found", "message": "No fairness requirements spec for project"}
    return {
        "frs_id": frs.frs_id,
        "project_id": frs.project_id,
        "requirements": frs.requirements,
        "version": frs.version,
    }


# ─── Evidence Packages ──────────────────────────

@router.post("/projects/{project_id}/evidence", status_code=201)
async def create_evidence_package(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = EvidencePackageRepository(db)
    evidence_id = body.get("evidence_id", generate_id("fe_"))
    await repo.create(
        evidence_id=evidence_id,
        project_id=project_id,
        environment=body.get("environment", "dev"),
        evidence_type=body.get("evidence_type", "manual_review"),
        evidence_data=body.get("evidence_data"),
        attestation_status=body.get("attestation_status", "unsigned"),
    )
    await db.commit()
    return {"evidence_id": evidence_id, "project_id": project_id, "status": "created"}


@router.get("/projects/{project_id}/evidence", status_code=200)
async def list_evidence_packages(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = EvidencePackageRepository(db)
    packages = await repo.list_by_project(project_id)
    return [
        {
            "evidence_id": e.evidence_id,
            "environment": e.environment,
            "evidence_type": e.evidence_type,
            "attestation_status": e.attestation_status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in packages
    ]


@router.post("/projects/{project_id}/evidence/{evidence_id}/sign", status_code=200)
async def sign_attestation(
    project_id: str,
    evidence_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = EvidencePackageRepository(db)
    evidence = await repo.get(evidence_id)
    if not evidence:
        return {"error": "Evidence package not found"}
    await repo.update(evidence, attestation_status="signed")
    await db.commit()
    return {"evidence_id": evidence_id, "attestation_status": "signed", "signed_by": body.get("signed_by")}


# ─── Fairness Exceptions ──────────────────────

@router.post("/projects/{project_id}/fairness-exceptions", status_code=201)
async def create_fairness_exception(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = FairnessExceptionRepository(db)
    exception_id = body.get("exception_id", generate_id("fer_"))
    await repo.create(
        exception_id=exception_id,
        project_id=project_id,
        requirement_id=body.get("requirement_id"),
        rationale=body.get("rationale", ""),
        compensating_controls=body.get("compensating_controls"),
        status=body.get("status", "pending"),
    )
    await db.commit()
    return {"exception_id": exception_id, "project_id": project_id, "status": "created"}


# ─── Monitoring Signals ──────────────────────

@router.post("/monitoring/signals", status_code=201)
async def ingest_monitoring_signal(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = MonitoringSignalRepository(db)
    signal_id = body.get("signal_id", generate_id("sig_"))
    await repo.create(
        signal_id=signal_id,
        project_id=body["project_id"],
        environment=body.get("environment", "dev"),
        signal_type=body["signal_type"],
        value=body["value"],
        threshold=body.get("threshold"),
        metadata_json=body.get("metadata"),
        recorded_at=datetime.now(timezone.utc),
    )
    await db.commit()
    return {"signal_id": signal_id, "status": "recorded"}


@router.get("/monitoring/signals", status_code=200)
async def query_monitoring_signals(
    project_id: str,
    signal_type: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = MonitoringSignalRepository(db)
    if signal_type:
        signals = await repo.list_by_project_and_type(project_id, signal_type)
    else:
        signals = await repo.list_by_field("project_id", project_id)
    return [
        {
            "signal_id": s.signal_id,
            "signal_type": s.signal_type,
            "value": s.value,
            "threshold": s.threshold,
            "recorded_at": s.recorded_at.isoformat() if s.recorded_at else None,
        }
        for s in signals
    ]
