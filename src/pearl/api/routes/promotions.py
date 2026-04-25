"""Promotion gate evaluation and history routes."""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Request

logger = logging.getLogger(__name__)
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.errors.exceptions import ValidationError
from pearl.models.enums import ApprovalDecisionValue, ApprovalRequestType, ApprovalStatus, PromotionRequestStatus
from pearl.repositories.approval_repo import ApprovalDecisionRepository, ApprovalRequestRepository
from pearl.repositories.exception_repo import ExceptionRepository
from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
from pearl.repositories.promotion_repo import (
    PromotionEvaluationRepository,
    PromotionGateRepository,
    PromotionHistoryRepository,
)
from pearl.repositories.fairness_repo import AuditEventRepository
from pearl.services.id_generator import generate_id
from pearl.services.promotion.gate_evaluator import evaluate_promotion, _build_eval_context
from pearl.api.routes.stream import publish_event

router = APIRouter(tags=["Promotions"])


class EvaluatePromotionBody(BaseModel):
    source_environment: str | None = None
    target_environment: str | None = None
    commit_sha: str | None = None
    version_tag: str | None = None
    branch: str | None = None


class RequestPromotionBody(BaseModel):
    source_environment: str | None = None
    target_environment: str | None = None
    commit_sha: str | None = None
    version_tag: str | None = None
    branch: str | None = None


def _schedule_anomaly_checks(
    background_tasks: BackgroundTasks,
    request,
    project_id: str,
    promotion_time,
    trace_id: str,
) -> None:
    """Schedule AGP-02 and AGP-05 anomaly checks as background tasks post-response."""
    session_factory = getattr(getattr(request, "app", None), "state", None)
    session_factory = getattr(session_factory, "db_session_factory", None) if session_factory else None
    user_sub = "unknown"
    if request and hasattr(request, "state") and hasattr(request.state, "user"):
        user_sub = (request.state.user or {}).get("sub", "unknown")
    if not session_factory:
        return

    async def _agp02(sf=session_factory, pid=project_id, pt=promotion_time, sub=user_sub, tid=trace_id):
        from pearl.security.anomaly_detector import detect_agp02_rapid_promotion, emit_detection
        async with sf() as s:
            result = await detect_agp02_rapid_promotion(s, pid, pt, sub, tid)
            if result:
                emit_detection(result)

    async def _agp05(sf=session_factory, pid=project_id, at=promotion_time, sub=user_sub, tid=trace_id):
        from pearl.security.anomaly_detector import detect_agp05_missing_receipt, emit_detection
        async with sf() as s:
            result = await detect_agp05_missing_receipt(s, pid, at, sub, tid)
            if result:
                emit_detection(result)

    background_tasks.add_task(_agp02)
    background_tasks.add_task(_agp05)


@router.post("/projects/{project_id}/promotions/evaluate", status_code=200)
async def evaluate_promotion_readiness(
    project_id: str,
    body: EvaluatePromotionBody = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    body = body or EvaluatePromotionBody()
    evaluation = await evaluate_promotion(
        project_id=project_id,
        source_environment=body.source_environment,
        target_environment=body.target_environment,
        trace_id=trace_id,
        session=db,
    )
    # Store version fields on the persisted evaluation row
    eval_repo = PromotionEvaluationRepository(db)
    eval_row = await eval_repo.get(evaluation.evaluation_id)
    if eval_row and (body.commit_sha or body.version_tag or body.branch):
        await eval_repo.update(
            eval_row,
            commit_sha=body.commit_sha,
            version_tag=body.version_tag,
            branch=body.branch,
        )
    await db.commit()
    result = evaluation.model_dump(mode="json", exclude_none=True)
    # Attach version fields to the response
    result["commit_sha"] = body.commit_sha
    result["version_tag"] = body.version_tag
    result["branch"] = body.branch
    # AIUC-1 compliance summary — build context separately to extract AIUC fields
    try:
        from pearl.repositories.project_repo import ProjectRepository
        proj = await ProjectRepository(db).get(project_id)
        if proj:
            aiuc_ctx = await _build_eval_context(project_id, proj, db)
            result["aiuc_compliance"] = {
                "score_pct": aiuc_ctx.aiuc_score_pct,
                "satisfied_count": aiuc_ctx.aiuc_satisfied_count,
                "mandatory_count": aiuc_ctx.aiuc_mandatory_count,
                "outstanding": aiuc_ctx.aiuc_outstanding,
                "hints": aiuc_ctx.aiuc_hints,
            }
    except Exception as _aiuc_exc:
        logger.warning("AIUC enrichment failed for project %s", project_id, exc_info=True)
        result["aiuc_compliance"] = {"error": "enrichment_failed", "detail": str(_aiuc_exc)}
    # Publish real-time event so connected clients update without polling
    if request:
        redis = getattr(request.app.state, "redis", None)
        await publish_event(redis, "gate_evaluated", {
            "project_id": project_id,
            "evaluation_id": evaluation.evaluation_id,
            "status": evaluation.status,
            "passed_count": evaluation.passed_count,
            "failed_count": evaluation.failed_count,
            "source_environment": evaluation.source_environment,
            "target_environment": evaluation.target_environment,
        })
    return result


@router.get("/projects/{project_id}/promotions/readiness", status_code=200)
async def get_promotion_readiness(
    project_id: str,
    target_environment: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = PromotionEvaluationRepository(db)
    if target_environment:
        evaluation = await repo.get_latest_by_project_and_target(project_id, target_environment)
    else:
        evaluation = await repo.get_latest_by_project(project_id)
    if not evaluation:
        return {"status": "not_evaluated", "message": "No promotion evaluation found. Run evaluate first."}
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
        "commit_sha": evaluation.commit_sha,
        "version_tag": evaluation.version_tag,
        "branch": evaluation.branch,
    }


@router.get("/projects/{project_id}/promotions/aiuc-compliance")
async def get_aiuc_compliance(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return AIUC-1 compliance status for a project without full gate evaluation."""
    from pearl.services.promotion.aiuc_mapping import AIUC1_MANDATORY_PILOT
    from pearl.repositories.project_repo import ProjectRepository

    proj = await ProjectRepository(db).get(project_id)
    if not proj:
        raise NotFoundError("Project", project_id)

    ctx = await _build_eval_context(project_id, proj, db)
    return {
        "project_id": project_id,
        "score_pct": ctx.aiuc_score_pct,
        "satisfied_count": ctx.aiuc_satisfied_count,
        "mandatory_count": ctx.aiuc_mandatory_count,
        "outstanding": ctx.aiuc_outstanding,
        "hints": ctx.aiuc_hints,
        "mandatory_controls": AIUC1_MANDATORY_PILOT,
    }


@router.post("/projects/{project_id}/promotions/request", status_code=202)
async def request_promotion(
    project_id: str,
    background_tasks: BackgroundTasks,
    body: RequestPromotionBody = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    body = body or RequestPromotionBody()

    # ── Sequential gate enforcement ──────────────────────────────────────────
    # Pipeline: pilot → dev → prod. Load the project's current_environment and
    # determine the correct next gate. Gate skipping is rejected before any
    # evaluation or approval record is created.
    from pearl.repositories.project_repo import ProjectRepository as _ProjRepo
    from pearl.services.promotion.gate_evaluator import next_environment as _next_env
    _proj = await _ProjRepo(db).get(project_id)
    if not _proj:
        raise ValidationError(f"Project '{project_id}' not found")
    _current = _proj.current_environment
    if not _current:
        from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository as _EnvProfileRepo
        _ep = await _EnvProfileRepo(db).get_by_project(project_id)
        _current = _ep.environment if _ep else "pilot"
    _requested_target = body.target_environment if body else None
    _expected_target = await _next_env(_current, db)
    if _expected_target is None:
        raise ValidationError(
            f"Project '{project_id}' is already at the final environment ('{_current}'). "
            "No further promotion is possible."
        )
    if _requested_target and _requested_target != _expected_target:
        raise ValidationError(
            f"Cannot promote to '{_requested_target}': project is at '{_current}', next valid target is '{_expected_target}'."
        )
    # ─────────────────────────────────────────────────────────────────────────

    # Evaluate first — evaluate_promotion will use project.current_environment
    # as the authoritative source, so the gate it selects will always be the
    # correct next step for this project's actual position in the pipeline.
    evaluation = await evaluate_promotion(
        project_id=project_id,
        trace_id=trace_id,
        session=db,
        target_environment=_requested_target or _expected_target,
    )
    # Store version fields on the evaluation row
    eval_repo = PromotionEvaluationRepository(db)
    eval_row = await eval_repo.get(evaluation.evaluation_id)
    if eval_row and (body.commit_sha or body.version_tag or body.branch):
        await eval_repo.update(
            eval_row,
            commit_sha=body.commit_sha,
            version_tag=body.version_tag,
            branch=body.branch,
        )

    # Check the gate's approval_mode
    gate_repo = PromotionGateRepository(db)
    gate = await gate_repo.get(evaluation.gate_id)
    approval_mode = gate.approval_mode if gate else "manual"

    # Create approval request
    approval_repo = ApprovalRequestRepository(db)
    approval_id = generate_id("appr_")

    evaluation_passed = evaluation.status == "passed"

    # Trust accumulation auto-pass path: gate has earned auto-pass via accumulated trust
    if evaluation.auto_pass and evaluation_passed:
        await approval_repo.create(
            approval_request_id=approval_id,
            project_id=project_id,
            request_type=ApprovalRequestType.PROMOTION_GATE,
            environment=evaluation.target_environment,
            status=ApprovalStatus.APPROVED,
            request_data={
                "evaluation_id": evaluation.evaluation_id,
                "gate_id": evaluation.gate_id,
                "source_environment": evaluation.source_environment,
                "target_environment": evaluation.target_environment,
                "progress_pct": evaluation.progress_pct,
                "auto_pass": True,
            },
            trace_id=trace_id,
        )

        decision_repo = ApprovalDecisionRepository(db)
        await decision_repo.create(
            approval_request_id=approval_id,
            decision=ApprovalDecisionValue.APPROVE,
            decided_by="pearl-trust-auto-pass",
            decider_role="system",
            reason="Auto-approved: gate has accumulated sufficient trust (auto_pass=True, no open drift_trend findings)",
            decided_at=datetime.now(timezone.utc),
            trace_id=trace_id,
        )

        history_repo = PromotionHistoryRepository(db)
        await history_repo.create(
            history_id=generate_id("promhist_"),
            project_id=project_id,
            source_environment=evaluation.source_environment,
            target_environment=evaluation.target_environment,
            evaluation_id=evaluation.evaluation_id,
            promoted_by="pearl-trust-auto-pass",
            promoted_at=datetime.now(timezone.utc),
            details={"auto_approved": True, "auto_pass": True, "approval_request_id": approval_id},
        )

        env_repo = EnvironmentProfileRepository(db)
        env_profile = await env_repo.get_by_project(project_id)
        if env_profile:
            env_profile.environment = evaluation.target_environment
        else:
            await env_repo.create(
                profile_id=generate_id("envprof_"),
                project_id=project_id,
                environment=evaluation.target_environment,
                delivery_stage="bootstrap",
                risk_level="low",
                autonomy_mode="assistive",
            )

        status = PromotionRequestStatus.APPROVED
        await AuditEventRepository(db).append(
            event_id=generate_id("evt_"),
            resource_id=approval_id,
            action_type="promotion.requested",
            actor=getattr(getattr(request, "state", None), "user", {}).get("sub") if request else None,
            details={
                "project_id": project_id,
                "source_environment": evaluation.source_environment,
                "target_environment": evaluation.target_environment,
                "auto_pass": True,
                "trace_id": trace_id,
            },
        )
        await db.commit()

        _schedule_anomaly_checks(background_tasks, request, project_id, datetime.now(timezone.utc), trace_id)
        return {
            "request_id": generate_id("promreq_"),
            "project_id": project_id,
            "evaluation_id": evaluation.evaluation_id,
            "approval_request_id": approval_id,
            "status": status.value,
            "auto_approved": True,
            "auto_pass": True,
            "source_environment": evaluation.source_environment,
            "target_environment": evaluation.target_environment,
            "progress_pct": evaluation.progress_pct,
            "blockers": evaluation.blockers,
        }

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
                "gate_id": evaluation.gate_id,
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
            commit_sha=body.commit_sha,
            version_tag=body.version_tag,
            branch=body.branch,
        )

        # Update both the project row (authoritative) and env_profile (legacy sync)
        from pearl.repositories.project_repo import ProjectRepository as _ProjRepo
        _proj_repo = _ProjRepo(db)
        _proj = await _proj_repo.get(project_id)
        if _proj:
            await _proj_repo.update(_proj, current_environment=evaluation.target_environment)

        env_repo = EnvironmentProfileRepository(db)
        env_profile = await env_repo.get_by_project(project_id)
        if env_profile:
            env_profile.environment = evaluation.target_environment
        else:
            await env_repo.create(
                profile_id=generate_id("envprof_"),
                project_id=project_id,
                environment=evaluation.target_environment,
                delivery_stage="bootstrap",
                risk_level="low",
                autonomy_mode="assistive",
            )

        status = PromotionRequestStatus.APPROVED
        await AuditEventRepository(db).append(
            event_id=generate_id("evt_"),
            resource_id=approval_id,
            action_type="promotion.requested",
            actor=getattr(getattr(request, "state", None), "user", {}).get("sub") if request else None,
            details={
                "project_id": project_id,
                "source_environment": evaluation.source_environment,
                "target_environment": evaluation.target_environment,
                "auto_approved": True,
                "trace_id": trace_id,
            },
        )
        await db.commit()

        _schedule_anomaly_checks(background_tasks, request, project_id, datetime.now(timezone.utc), trace_id)
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
            "gate_id": evaluation.gate_id,
            "source_environment": evaluation.source_environment,
            "target_environment": evaluation.target_environment,
            "progress_pct": evaluation.progress_pct,
        },
        trace_id=trace_id,
    )

    status = PromotionRequestStatus.PENDING_APPROVAL if evaluation_passed else PromotionRequestStatus.EVALUATION_FAILED
    await AuditEventRepository(db).append(
        event_id=generate_id("evt_"),
        resource_id=approval_id,
        action_type="promotion.requested",
        actor=getattr(getattr(request, "state", None), "user", {}).get("sub") if request else None,
        details={
            "project_id": project_id,
            "source_environment": evaluation.source_environment,
            "target_environment": evaluation.target_environment,
            "auto_approved": False,
            "trace_id": trace_id,
        },
    )
    await db.commit()

    _schedule_anomaly_checks(background_tasks, request, project_id, datetime.now(timezone.utc), trace_id)
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
            "commit_sha": h.commit_sha,
            "version_tag": h.version_tag,
            "branch": h.branch,
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
            "auto_pass": g.auto_pass,
            "pass_count": g.pass_count,
            "auto_pass_threshold": g.auto_pass_threshold,
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
        "auto_pass": gate.auto_pass,
        "pass_count": gate.pass_count,
        "auto_pass_threshold": gate.auto_pass_threshold,
    }


@router.patch("/promotions/gates/{gate_id}", status_code=200)
async def update_gate_trust_config(
    gate_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update trust accumulation config for a gate. Admin only."""
    from pearl.errors.exceptions import ValidationError as PearlValidationError

    repo = PromotionGateRepository(db)
    gate = await repo.get(gate_id)
    if not gate:
        raise NotFoundError("Promotion gate", gate_id)

    if "auto_pass_threshold" in body:
        threshold = body["auto_pass_threshold"]
        if not isinstance(threshold, int) or threshold < 1:
            raise PearlValidationError("auto_pass_threshold must be a positive integer")
        gate.auto_pass_threshold = threshold

    if "auto_pass" in body:
        gate.auto_pass = bool(body["auto_pass"])

    await db.commit()
    return {
        "gate_id": gate_id,
        "auto_pass": gate.auto_pass,
        "pass_count": gate.pass_count,
        "auto_pass_threshold": gate.auto_pass_threshold,
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


@router.post("/projects/{project_id}/promotions/contest-rule", status_code=201)
async def contest_gate_rule(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Contest a failing gate rule by creating an exception + approval request."""
    evaluation_id = body.get("evaluation_id")
    rule_type = body.get("rule_type")
    contest_type = body.get("contest_type")
    rationale = body.get("rationale", "")

    if not evaluation_id or not rule_type or not contest_type:
        raise ValidationError("evaluation_id, rule_type, and contest_type are required")
    if contest_type not in ("false_positive", "risk_acceptance", "needs_more_time"):
        raise ValidationError("contest_type must be one of: false_positive, risk_acceptance, needs_more_time")

    eval_repo = PromotionEvaluationRepository(db)
    evaluation = await eval_repo.get(evaluation_id)
    if not evaluation or evaluation.project_id != project_id:
        raise NotFoundError("Promotion evaluation", evaluation_id)

    compensating_controls = body.get("compensating_controls") or []
    expires_days = body.get("expires_days")

    # Auto-populate finding_ids from the stored rule evidence if not provided
    finding_ids = body.get("finding_ids") or []
    if not finding_ids:
        rule_results = evaluation.rule_results or []
        for rr in rule_results:
            rr_dict = rr if isinstance(rr, dict) else (rr.model_dump() if hasattr(rr, "model_dump") else {})
            if rr_dict.get("rule_type") == rule_type:
                finding_ids = (rr_dict.get("evidence") or {}).get("finding_ids", [])
                break

    now = datetime.now(timezone.utc)
    expires_at = None
    if expires_days:
        from datetime import timedelta
        expires_at = now + timedelta(days=int(expires_days))

    # Create exception record (pending until approved)
    exc_repo = ExceptionRepository(db)
    exception_id = generate_id("exc_")
    await exc_repo.create(
        exception_id=exception_id,
        project_id=project_id,
        scope={"controls": [rule_type], "environment": evaluation.source_environment},
        status="pending",
        requested_by="dashboard-user",
        rationale=rationale,
        compensating_controls=compensating_controls or None,
        approved_by=None,
        start_at=None,
        expires_at=expires_at,
        review_cadence_days=None,
        trace_id=trace_id,
    )

    # Create approval request for the exception
    approval_repo = ApprovalRequestRepository(db)
    approval_id = generate_id("appr_")
    await approval_repo.create(
        approval_request_id=approval_id,
        project_id=project_id,
        request_type=ApprovalRequestType.EXCEPTION,
        environment=evaluation.source_environment,
        status=ApprovalStatus.PENDING,
        request_data={
            "exception_id": exception_id,
            "evaluation_id": evaluation_id,
            "rule_type": rule_type,
            "contest_type": contest_type,
            "finding_ids": finding_ids,
            "rationale": rationale,
            "compensating_controls": compensating_controls,
        },
        trace_id=trace_id,
    )

    await db.commit()

    return {
        "exception_id": exception_id,
        "approval_request_id": approval_id,
        "status": "pending",
    }


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
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.services.id_generator import generate_id as _gen_id

    # Require admin role — emit BA-06 finding before blocking
    if request:
        user = getattr(request.state, "user", {})
        if "admin" not in user.get("roles", []):
            # BA-06: unauthorized promotion attempt
            _from_env = body.get("from_environment", "unknown")
            _find_repo = FindingRepository(db)
            await _find_repo.create(
                finding_id=_gen_id("find_"),
                project_id=project_id,
                environment=_from_env,
                category="governance",
                severity="high",
                title="Unauthorized Promotion Attempt (BA-06)",
                source={"system": "pearl-promotion-gate"},
                full_data={"attempted_by": user.get("sub", "unknown"), "roles": user.get("roles", [])},
                normalized=True,
                detected_at=datetime.now(timezone.utc),
                anomaly_code="BA-06",
                status="open",
                schema_version="1.1",
            )
            await db.commit()
            raise AuthorizationError("Admin role required for rollback")

    from_environment = body.get("from_environment")
    reason = body.get("reason", "")

    if not from_environment:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError("from_environment is required")

    history_id = generate_id("hist_")
    now = datetime.now(timezone.utc)

    history_repo = PromotionHistoryRepository(db)
    promoted_by = getattr(getattr(request, "state", None), "user", {}).get("sub", "system") if request else "system"
    await history_repo.create(
        history_id=history_id,
        project_id=project_id,
        source_environment=from_environment,
        target_environment="rollback",
        evaluation_id="rollback",
        promoted_by=promoted_by,
        promoted_at=now,
        details={
            "type": "rollback",
            "reason": reason,
            "trace_id": trace_id,
        },
    )

    # Update current_environment on ProjectRow to reflect demotion
    from pearl.repositories.project_repo import ProjectRepository as _ProjRepo
    _proj = await _ProjRepo(db).get(project_id)
    if _proj:
        await _ProjRepo(db).update(_proj, current_environment="rollback")

    await db.commit()

    # Emit SSE demotion event
    if request:
        _redis = getattr(request.app.state, "redis", None)
        await publish_event(_redis, "auto_demotion", {
            "project_id": project_id,
            "history_id": history_id,
            "type": "rollback",
            "from_environment": from_environment,
            "triggered_by": promoted_by,
        })

    return {
        "history_id": history_id,
        "project_id": project_id,
        "type": "rollback",
        "from_environment": from_environment,
        "reason": reason,
        "rolled_back_at": now.isoformat(),
    }


@router.post("/projects/{project_id}/promotions/reset-to-sandbox", status_code=200)
async def reset_to_sandbox(
    project_id: str,
    body: dict = None,
    request=None,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Reset a project back to pilot, clearing all promotion history and evaluations.

    Admin-only. Use this to start the promotion pipeline from scratch — useful after
    significant architectural changes or when re-validating with new gate tools.
    """
    from pearl.errors.exceptions import AuthorizationError, NotFoundError
    from pearl.repositories.project_repo import ProjectRepository as _ProjRepo
    from sqlalchemy import delete

    body = body or {}

    if request:
        user = getattr(request.state, "user", {})
        if "admin" not in user.get("roles", []):
            raise AuthorizationError("Admin role required for reset-to-sandbox")

    proj_repo = _ProjRepo(db)
    project = await proj_repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    reason = body.get("reason", "Manual reset to pilot")
    promoted_by = getattr(getattr(request, "state", None), "user", {}).get("sub", "system") if request else "system"
    now = datetime.now(timezone.utc)

    # Record the reset as a history entry
    history_id = generate_id("hist_")
    history_repo = PromotionHistoryRepository(db)
    await history_repo.create(
        history_id=history_id,
        project_id=project_id,
        source_environment=project.current_environment or "unknown",
        target_environment="pilot",
        evaluation_id="reset",
        promoted_by=promoted_by,
        promoted_at=now,
        details={
            "type": "reset_to_pilot",
            "reason": reason,
            "trace_id": trace_id,
            "previous_environment": project.current_environment,
        },
    )

    # Clear all prior evaluations and history (except this reset entry) if requested
    clear_history = body.get("clear_history", True)
    if clear_history:
        from pearl.db.models.promotion import PromotionEvaluationRow, PromotionHistoryRow
        await db.execute(
            delete(PromotionEvaluationRow).where(PromotionEvaluationRow.project_id == project_id)
        )
        await db.execute(
            delete(PromotionHistoryRow)
            .where(PromotionHistoryRow.project_id == project_id)
            .where(PromotionHistoryRow.history_id != history_id)
        )

    # Set current environment to pilot on both the project row and env_profile
    # so that all environment reads agree after a reset.
    await proj_repo.update(project, current_environment="pilot")
    env_profile = await EnvironmentProfileRepository(db).get_by_project(project_id)
    if env_profile:
        env_profile.environment = "pilot"
    await db.commit()

    # Emit SSE event
    if request:
        _redis = getattr(request.app.state, "redis", None)
        await publish_event(_redis, "project_reset", {
            "project_id": project_id,
            "target_environment": "pilot",
            "triggered_by": promoted_by,
        })

    return {
        "project_id": project_id,
        "type": "reset_to_pilot",
        "current_environment": "pilot",
        "reason": reason,
        "history_cleared": clear_history,
        "reset_at": now.isoformat(),
        "next_step": f"POST /api/v1/projects/{project_id}/promotions/evaluate to begin elevation from pilot → dev",
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
