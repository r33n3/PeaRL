"""Promotion gate evaluation and history routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.models.enums import ApprovalDecisionValue, ApprovalRequestType, ApprovalStatus, PromotionRequestStatus
from pearl.repositories.approval_repo import ApprovalDecisionRepository, ApprovalRequestRepository
from pearl.repositories.promotion_repo import (
    PromotionEvaluationRepository,
    PromotionGateRepository,
    PromotionHistoryRepository,
)
from pearl.services.id_generator import generate_id
from pearl.services.promotion.gate_evaluator import evaluate_promotion

router = APIRouter(tags=["Promotions"])


@router.post("/projects/{project_id}/promotions/evaluate", status_code=200)
async def evaluate_promotion_readiness(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    evaluation = await evaluate_promotion(
        project_id=project_id,
        trace_id=trace_id,
        session=db,
    )
    await db.commit()
    return evaluation.model_dump(mode="json", exclude_none=True)


@router.get("/projects/{project_id}/promotions/readiness", status_code=200)
async def get_promotion_readiness(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = PromotionEvaluationRepository(db)
    evaluation = await repo.get_latest_by_project(project_id)
    if not evaluation:
        return {"status": "no_evaluation", "message": "No promotion evaluation found. Run evaluate first."}
    return {
        "evaluation_id": evaluation.evaluation_id,
        "project_id": evaluation.project_id,
        "source_environment": evaluation.source_environment,
        "target_environment": evaluation.target_environment,
        "status": evaluation.status,
        "passed_count": evaluation.passed_count,
        "failed_count": evaluation.failed_count,
        "total_count": evaluation.total_count,
        "progress_pct": evaluation.progress_pct,
        "blockers": evaluation.blockers,
        "rule_results": evaluation.rule_results,
        "evaluated_at": evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else None,
    }


@router.post("/projects/{project_id}/promotions/request", status_code=202)
async def request_promotion(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    # Evaluate first
    evaluation = await evaluate_promotion(
        project_id=project_id,
        trace_id=trace_id,
        session=db,
    )

    # Check the gate's approval_mode
    gate_repo = PromotionGateRepository(db)
    gate = await gate_repo.get(evaluation.gate_id)
    approval_mode = gate.approval_mode if gate else "manual"

    # Create approval request
    approval_repo = ApprovalRequestRepository(db)
    approval_id = generate_id("appr_")

    evaluation_passed = evaluation.status == "passed"

    # Auto-approval path: gate is set to "auto" AND evaluation passed
    if approval_mode == "auto" and evaluation_passed:
        # Create approval request as already approved
        await approval_repo.create(
            approval_request_id=approval_id,
            project_id=project_id,
            request_type=ApprovalRequestType.PROMOTION_GATE,
            environment=evaluation.target_environment,
            status=ApprovalStatus.APPROVED,
            request_data={
                "evaluation_id": evaluation.evaluation_id,
                "source_environment": evaluation.source_environment,
                "target_environment": evaluation.target_environment,
                "progress_pct": evaluation.progress_pct,
            },
            trace_id=trace_id,
        )

        # Auto-create an approval decision
        decision_repo = ApprovalDecisionRepository(db)
        await decision_repo.create(
            approval_request_id=approval_id,
            decision=ApprovalDecisionValue.APPROVE,
            decided_by="pearl-auto-approval",
            decider_role="system",
            reason="Auto-approved: gate approval_mode is 'auto' and all rules passed",
            decided_at=datetime.now(timezone.utc),
            trace_id=trace_id,
        )

        # Create promotion history entry
        history_repo = PromotionHistoryRepository(db)
        await history_repo.create(
            history_id=generate_id("promhist_"),
            project_id=project_id,
            source_environment=evaluation.source_environment,
            target_environment=evaluation.target_environment,
            evaluation_id=evaluation.evaluation_id,
            promoted_by="pearl-auto-approval",
            promoted_at=datetime.now(timezone.utc),
            details={"auto_approved": True, "approval_request_id": approval_id},
        )

        status = PromotionRequestStatus.APPROVED
        await db.commit()

        return {
            "request_id": generate_id("promreq_"),
            "project_id": project_id,
            "evaluation_id": evaluation.evaluation_id,
            "approval_request_id": approval_id,
            "status": status.value,
            "auto_approved": True,
            "source_environment": evaluation.source_environment,
            "target_environment": evaluation.target_environment,
            "progress_pct": evaluation.progress_pct,
            "blockers": evaluation.blockers,
        }

    # Manual approval path (default): create PENDING approval request
    await approval_repo.create(
        approval_request_id=approval_id,
        project_id=project_id,
        request_type=ApprovalRequestType.PROMOTION_GATE,
        environment=evaluation.target_environment,
        status=ApprovalStatus.PENDING,
        request_data={
            "evaluation_id": evaluation.evaluation_id,
            "source_environment": evaluation.source_environment,
            "target_environment": evaluation.target_environment,
            "progress_pct": evaluation.progress_pct,
        },
        trace_id=trace_id,
    )

    status = PromotionRequestStatus.PENDING_APPROVAL if evaluation_passed else PromotionRequestStatus.EVALUATION_FAILED
    await db.commit()

    return {
        "request_id": generate_id("promreq_"),
        "project_id": project_id,
        "evaluation_id": evaluation.evaluation_id,
        "approval_request_id": approval_id,
        "status": status.value,
        "auto_approved": False,
        "source_environment": evaluation.source_environment,
        "target_environment": evaluation.target_environment,
        "progress_pct": evaluation.progress_pct,
        "blockers": evaluation.blockers,
    }


@router.get("/projects/{project_id}/promotions/history", status_code=200)
async def get_promotion_history(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = PromotionHistoryRepository(db)
    history = await repo.list_by_project(project_id)
    return [
        {
            "history_id": h.history_id,
            "source_environment": h.source_environment,
            "target_environment": h.target_environment,
            "promoted_by": h.promoted_by,
            "promoted_at": h.promoted_at.isoformat() if h.promoted_at else None,
        }
        for h in history
    ]


@router.get("/promotions/gates", status_code=200)
async def list_default_gates(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    repo = PromotionGateRepository(db)
    gates = await repo.list_all_defaults()
    return [
        {
            "gate_id": g.gate_id,
            "source_environment": g.source_environment,
            "target_environment": g.target_environment,
            "approval_mode": g.approval_mode or "manual",
            "rules": g.rules if isinstance(g.rules, list) else [],
            "rule_count": len(g.rules) if isinstance(g.rules, list) else 0,
        }
        for g in gates
    ]


@router.get("/promotions/gates/{gate_id}", status_code=200)
async def get_gate(
    gate_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a single promotion gate with full details."""
    repo = PromotionGateRepository(db)
    gate = await repo.get(gate_id)
    if not gate:
        raise NotFoundError("Promotion gate", gate_id)
    return {
        "gate_id": gate.gate_id,
        "source_environment": gate.source_environment,
        "target_environment": gate.target_environment,
        "approval_mode": gate.approval_mode or "manual",
        "rules": gate.rules if isinstance(gate.rules, list) else [],
        "rule_count": len(gate.rules) if isinstance(gate.rules, list) else 0,
    }


@router.post("/promotions/gates", status_code=201)
async def create_or_update_gate(
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = PromotionGateRepository(db)
    gate_id = body.get("gate_id", generate_id("gate_"))
    existing = await repo.get(gate_id)

    if existing:
        await repo.update(existing, rules=body.get("rules", existing.rules))
        await db.commit()
        return {"gate_id": gate_id, "action": "updated"}
    else:
        await repo.create(
            gate_id=gate_id,
            source_environment=body["source_environment"],
            target_environment=body["target_environment"],
            project_id=body.get("project_id"),
            rules=body.get("rules", []),
        )
        await db.commit()
        return {"gate_id": gate_id, "action": "created"}


@router.delete("/promotions/gates/{gate_id}", status_code=204)
async def delete_gate(
    gate_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a promotion gate."""
    repo = PromotionGateRepository(db)
    gate = await repo.get(gate_id)
    if not gate:
        raise NotFoundError("Promotion gate", gate_id)
    await repo.delete(gate_id)
    await db.commit()


@router.post("/promotions/gates/{gate_id}/approval-mode")
async def update_gate_approval_mode(
    gate_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update the approval mode for a promotion gate."""
    mode = body.get("approval_mode", "manual")
    if mode not in ("auto", "manual"):
        raise ValueError("approval_mode must be 'auto' or 'manual'")

    gate_repo = PromotionGateRepository(db)
    gate = await gate_repo.get(gate_id)
    if not gate:
        raise NotFoundError("Promotion gate", gate_id)

    gate.approval_mode = mode
    await db.commit()

    return {"gate_id": gate_id, "approval_mode": mode}


@router.post("/projects/{project_id}/promotions/rollback", status_code=201)
async def rollback_promotion(
    project_id: str,
    body: dict,
    request=None,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Roll back a promotion for a project. Requires admin role."""
    from fastapi import Request
    from pearl.errors.exceptions import AuthorizationError

    # Require admin role
    if request:
        user = getattr(request.state, "user", {})
        if "admin" not in user.get("roles", []):
            raise AuthorizationError("Admin role required for rollback")

    from_environment = body.get("from_environment")
    reason = body.get("reason", "")

    if not from_environment:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError("from_environment is required")

    history_id = generate_id("hist_")
    now = datetime.now(timezone.utc)

    history_repo = PromotionHistoryRepository(db)
    await history_repo.create(
        history_id=history_id,
        project_id=project_id,
        source_environment=from_environment,
        target_environment="rollback",
        evaluation_id="rollback",
        promoted_by=getattr(getattr(request, "state", None), "user", {}).get("sub", "system") if request else "system",
        promoted_at=now,
        details={
            "type": "rollback",
            "reason": reason,
            "trace_id": trace_id,
        },
    )
    await db.commit()

    return {
        "history_id": history_id,
        "project_id": project_id,
        "type": "rollback",
        "from_environment": from_environment,
        "reason": reason,
        "rolled_back_at": now.isoformat(),
    }


@router.get("/projects/{project_id}/policy-history")
async def get_policy_history(
    project_id: str,
    resource_type: str = "org_baseline",
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return policy version history for a project resource."""
    from pearl.repositories.policy_version_repo import PolicyVersionRepository

    repo = PolicyVersionRepository(db)
    versions = await repo.list_for_resource(resource_type, project_id)

    return {
        "project_id": project_id,
        "resource_type": resource_type,
        "versions": [
            {
                "version_id": v.version_id,
                "version_number": v.version_number,
                "changed_by": v.changed_by,
                "change_summary": v.change_summary,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in versions
        ],
    }
