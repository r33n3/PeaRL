"""Elevation audit report generator."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.approval import ApprovalDecisionRow
from pearl.repositories.approval_repo import ApprovalDecisionRepository, ApprovalRequestRepository
from pearl.repositories.fairness_repo import EvidencePackageRepository
from pearl.repositories.promotion_repo import PromotionEvaluationRepository, PromotionHistoryRepository


async def generate_elevation_audit(project_id: str, request, db: AsyncSession) -> dict:
    """
    Full promotion package. Includes:
    - All promotion history for the project (from PromotionHistoryRepository)
    - For the latest promotion: gate evaluation + decision + decider + conditions
    - Evidence trail per gate rule (full_chain) or summary (compliance)
    - Approval decision from ApprovalDecisionRepository
    """
    generated_at = datetime.now(timezone.utc).isoformat()

    # Load all promotion history
    history_rows: list = []
    try:
        hist_repo = PromotionHistoryRepository(db)
        history_rows = await hist_repo.list_by_project(project_id)
    except Exception:
        pass

    # Load evaluations for full_chain detail
    evaluations_by_id: dict[str, object] = {}
    if request.detail_level == "full_chain":
        try:
            eval_repo = PromotionEvaluationRepository(db)
            for h in history_rows:
                if h.evaluation_id and h.evaluation_id not in evaluations_by_id:
                    ev = await eval_repo.get(h.evaluation_id)
                    if ev:
                        evaluations_by_id[h.evaluation_id] = ev
        except Exception:
            pass

    # Load approval decisions for full_chain
    decisions_by_request_id: dict[str, list[dict]] = {}
    if request.detail_level == "full_chain":
        try:
            appr_repo = ApprovalRequestRepository(db)
            all_approvals = await appr_repo.list_by_project(project_id)
            for appr in all_approvals:
                stmt = select(ApprovalDecisionRow).where(
                    ApprovalDecisionRow.approval_request_id == appr.approval_request_id
                )
                result = await db.execute(stmt)
                dec_rows = list(result.scalars().all())
                if dec_rows:
                    decisions_by_request_id[appr.approval_request_id] = [
                        {
                            "decision": d.decision,
                            "reason": d.reason,
                            "decider": d.decided_by,
                            "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                        }
                        for d in dec_rows
                    ]
        except Exception:
            pass

    # Load evidence packages for full_chain
    evidence_packages: list[dict] = []
    if request.detail_level == "full_chain":
        try:
            ev_repo = EvidencePackageRepository(db)
            ev_list = await ev_repo.list_by_project(project_id)
            for ev in ev_list:
                ev_data = ev.evidence_data or {}
                evidence_packages.append(
                    {
                        "evidence_id": ev.evidence_id,
                        "evidence_type": ev.evidence_type,
                        "environment": ev.environment,
                        "attestation_status": ev.attestation_status,
                        "submitted_at": ev.created_at.isoformat() if ev.created_at else None,
                        "artifact_refs": ev_data.get("artifact_refs", []),
                    }
                )
        except Exception:
            pass

    # Determine current environment from latest promotion
    current_environment = "unknown"
    if history_rows:
        latest_hist = sorted(
            history_rows,
            key=lambda h: h.promoted_at if h.promoted_at else datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[0]
        current_environment = latest_hist.target_environment

    # Build promotions list
    promotions: list[dict] = []
    for h in history_rows:
        entry: dict = {
            "history_id": h.history_id,
            "source_environment": h.source_environment,
            "target_environment": h.target_environment,
            "promoted_by": h.promoted_by,
            "promoted_at": h.promoted_at.isoformat() if h.promoted_at else None,
            "evaluation_id": h.evaluation_id,
            "details": h.details,
        }

        if request.detail_level == "full_chain":
            # Attach gate evaluation
            ev_row = evaluations_by_id.get(h.evaluation_id)
            if ev_row:
                entry["gate_evaluation"] = {
                    "evaluation_id": ev_row.evaluation_id,
                    "status": ev_row.status,
                    "passed_count": ev_row.passed_count,
                    "failed_count": ev_row.failed_count,
                    "total_count": ev_row.total_count,
                    "progress_pct": ev_row.progress_pct,
                    "rule_results": ev_row.rule_results,
                    "blockers": ev_row.blockers,
                }

            # Attach approval decisions for this project
            all_decisions: list[dict] = []
            for decisions in decisions_by_request_id.values():
                all_decisions.extend(decisions)
            entry["approval_decision"] = all_decisions[0] if all_decisions else None

            # Attach evidence submitted
            entry["evidence_submitted"] = evidence_packages

        promotions.append(entry)

    return {
        "project_id": project_id,
        "detail_level": request.detail_level,
        "generated_at": generated_at,
        "promotions": promotions,
        "current_environment": current_environment,
    }
