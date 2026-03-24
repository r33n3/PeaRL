"""Gate fulfillment report generator."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.repositories.approval_repo import ApprovalRequestRepository
from pearl.repositories.fairness_repo import EvidencePackageRepository
from pearl.repositories.promotion_repo import PromotionEvaluationRepository


async def generate_gate_fulfillment(project_id: str, request, db: AsyncSession) -> dict:
    """
    For each gate rule in the latest promotion evaluation:
    - compliance level: {gate_rule, status, message, evidence_count}
    - full_chain level: adds evidence_ids, artifact_refs, submitted_by, submitted_at, gate_reasoning
    """
    generated_at = datetime.now(timezone.utc).isoformat()

    # Load latest promotion evaluation
    evaluation = None
    target_env = "unknown"
    rule_results: list[dict] = []
    try:
        eval_repo = PromotionEvaluationRepository(db)
        evaluation = await eval_repo.get_latest_by_project(project_id)
        if evaluation:
            target_env = evaluation.target_environment
            raw_results = evaluation.rule_results or []
            if isinstance(raw_results, list):
                rule_results = raw_results
            elif isinstance(raw_results, dict):
                # Some evaluations store results as a dict keyed by rule
                rule_results = list(raw_results.values())
    except Exception:
        pass

    # Load evidence packages for full_chain
    evidence_by_type: dict[str, list[dict]] = {}
    if request.detail_level == "full_chain":
        try:
            ev_repo = EvidencePackageRepository(db)
            ev_list = await ev_repo.list_by_project(project_id)
            for ev in ev_list:
                etype = ev.evidence_type
                if etype not in evidence_by_type:
                    evidence_by_type[etype] = []
                ev_data = ev.evidence_data or {}
                evidence_by_type[etype].append(
                    {
                        "evidence_id": ev.evidence_id,
                        "evidence_type": etype,
                        "submitted_at": ev.created_at.isoformat() if ev.created_at else None,
                        "artifact_refs": ev_data.get("artifact_refs", []),
                    }
                )
        except Exception:
            pass

    # Load pending approval requests for this project
    approval_request_id: str | None = None
    try:
        appr_repo = ApprovalRequestRepository(db)
        pending = await appr_repo.list_by_project(project_id)
        for appr in pending:
            if appr.status == "pending":
                approval_request_id = appr.approval_request_id
                break
    except Exception:
        pass

    # Build gate rows
    gates: list[dict] = []
    passed_count = 0
    failed_count = 0
    blockers: list[str] = []

    for rule in rule_results:
        rule_name = rule.get("rule_type") or rule.get("rule") or "unknown"
        result_val = rule.get("result", "unknown")
        message = rule.get("message") or rule.get("description") or ""
        is_pass = result_val in ("pass", "passed", "skip", "exception")
        status = "pass" if is_pass else "fail"

        if is_pass:
            passed_count += 1
        else:
            failed_count += 1
            blockers.append(f"{rule_name}: {message}" if message else rule_name)

        gate_entry: dict = {
            "rule": rule_name,
            "status": status,
            "message": message,
            "evidence_count": 0,
        }

        if request.detail_level == "full_chain":
            # Attach any evidence that matches the rule name or is generally associated
            rule_evidence = evidence_by_type.get(rule_name, [])
            gate_entry["evidence_count"] = len(rule_evidence)
            gate_entry["evidence"] = rule_evidence
            gate_entry["gate_reasoning"] = rule.get("reasoning") or rule.get("reason") or ""

        gates.append(gate_entry)

    total = passed_count + failed_count
    pct = round((passed_count / total * 100), 1) if total > 0 else 0.0

    result: dict = {
        "project_id": project_id,
        "detail_level": request.detail_level,
        "environment_target": target_env,
        "generated_at": generated_at,
        "gate_summary": {
            "passed": passed_count,
            "failed": failed_count,
            "total": total,
            "pct": pct,
        },
        "gates": gates,
        "blockers": blockers,
        "approval_request_id": approval_request_id,
    }

    if evaluation:
        result["evaluation_id"] = evaluation.evaluation_id

    return result
