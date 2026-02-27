"""Project timeline API — chronological events from all sources."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.finding import FindingRow
from pearl.db.models.governance_telemetry import ClientAuditEventRow
from pearl.db.models.promotion import PromotionEvaluationRow, PromotionHistoryRow
from pearl.db.models.task_packet import TaskPacketRow
from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.project_repo import ProjectRepository

router = APIRouter(tags=["Timeline"])


@router.get("/projects/{project_id}/timeline")
async def get_project_timeline(
    project_id: str,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return chronological timeline of events for a project."""
    proj_repo = ProjectRepository(db)
    project = await proj_repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    events: list[dict] = []

    # 1. Finding detections (open + recently resolved)
    finding_stmt = select(FindingRow).where(
        FindingRow.project_id == project_id
    ).order_by(FindingRow.created_at.desc()).limit(limit)
    findings = list((await db.execute(finding_stmt)).scalars().all())
    for f in findings:
        if f.created_at:
            events.append({
                "event_id": f"finding_{f.finding_id}",
                "event_type": "finding_detected",
                "timestamp": f.created_at.isoformat(),
                "summary": f"Finding detected: [{f.severity}] {f.title or f.category}",
                "detail": {
                    "finding_id": f.finding_id,
                    "severity": f.severity,
                    "category": f.category,
                    "title": f.title,
                    "status": f.status,
                },
                "actor": (f.source or {}).get("tool_type", "scanner"),
                "finding_id": f.finding_id,
                "task_packet_id": None,
                "evaluation_id": None,
            })
        # Status change to resolved
        if f.status == "resolved" and f.updated_at and f.updated_at != f.created_at:
            events.append({
                "event_id": f"finding_resolved_{f.finding_id}",
                "event_type": "finding_resolved",
                "timestamp": f.updated_at.isoformat(),
                "summary": f"Finding resolved: {f.title or f.category}",
                "detail": {
                    "finding_id": f.finding_id,
                    "severity": f.severity,
                    "status": f.status,
                },
                "actor": "agent",
                "finding_id": f.finding_id,
                "task_packet_id": None,
                "evaluation_id": None,
            })

    # 2. TaskPacket events
    tp_stmt = select(TaskPacketRow).where(
        TaskPacketRow.project_id == project_id
    ).order_by(TaskPacketRow.created_at.desc()).limit(limit)
    packets = list((await db.execute(tp_stmt)).scalars().all())
    for p in packets:
        if p.created_at:
            events.append({
                "event_id": f"tp_created_{p.task_packet_id}",
                "event_type": "task_packet_created",
                "timestamp": p.created_at.isoformat(),
                "summary": f"Remediation task created: {(p.packet_data or {}).get('rule_type', 'unknown')}",
                "detail": {
                    "task_packet_id": p.task_packet_id,
                    "rule_type": (p.packet_data or {}).get("rule_type"),
                    "task_type": (p.packet_data or {}).get("task_type"),
                    "status": (p.packet_data or {}).get("status"),
                },
                "actor": "pearl_auto",
                "finding_id": None,
                "task_packet_id": p.task_packet_id,
                "evaluation_id": None,
            })
        if p.claimed_at:
            events.append({
                "event_id": f"tp_claimed_{p.task_packet_id}",
                "event_type": "agent_claimed",
                "timestamp": p.claimed_at.isoformat(),
                "summary": f"Agent claimed task: {(p.packet_data or {}).get('rule_type', 'unknown')}",
                "detail": {
                    "task_packet_id": p.task_packet_id,
                    "agent_id": p.agent_id,
                    "rule_type": (p.packet_data or {}).get("rule_type"),
                },
                "actor": f"agent:{p.agent_id}" if p.agent_id else "agent",
                "finding_id": None,
                "task_packet_id": p.task_packet_id,
                "evaluation_id": None,
            })
        if p.completed_at and p.outcome:
            outcome = p.outcome or {}
            events.append({
                "event_id": f"tp_completed_{p.task_packet_id}",
                "event_type": "agent_fixed",
                "timestamp": p.completed_at.isoformat(),
                "summary": outcome.get("fix_summary") or f"Agent completed task: {outcome.get('status', 'unknown')}",
                "detail": {
                    "task_packet_id": p.task_packet_id,
                    "fix_summary": outcome.get("fix_summary"),
                    "commit_ref": outcome.get("commit_ref"),
                    "files_changed": outcome.get("files_changed", []),
                    "finding_ids_resolved": outcome.get("finding_ids_resolved", []),
                    "status": outcome.get("status"),
                },
                "actor": f"agent:{p.agent_id}" if p.agent_id else "agent",
                "finding_id": None,
                "task_packet_id": p.task_packet_id,
                "evaluation_id": None,
            })

    # 3. Promotion evaluations
    eval_stmt = select(PromotionEvaluationRow).where(
        PromotionEvaluationRow.project_id == project_id
    ).order_by(PromotionEvaluationRow.evaluated_at.desc()).limit(20)
    evaluations = list((await db.execute(eval_stmt)).scalars().all())
    for e in evaluations:
        ts = e.evaluated_at or e.created_at
        if ts:
            events.append({
                "event_id": f"eval_{e.evaluation_id}",
                "event_type": "gate_evaluated",
                "timestamp": ts.isoformat(),
                "summary": f"Gate evaluated: {e.status} ({e.passed_count}/{e.total_count} rules passed)",
                "detail": {
                    "evaluation_id": e.evaluation_id,
                    "status": e.status,
                    "passed_count": e.passed_count,
                    "failed_count": e.failed_count,
                    "total_count": e.total_count,
                    "source_environment": e.source_environment,
                    "target_environment": e.target_environment,
                },
                "actor": "pearl_auto",
                "finding_id": None,
                "task_packet_id": None,
                "evaluation_id": e.evaluation_id,
            })

    # 4. Promotion history (elevations)
    history_stmt = select(PromotionHistoryRow).where(
        PromotionHistoryRow.project_id == project_id
    ).order_by(PromotionHistoryRow.promoted_at.desc()).limit(20)
    history = list((await db.execute(history_stmt)).scalars().all())
    for h in history:
        if h.promoted_at:
            events.append({
                "event_id": f"hist_{h.history_id}",
                "event_type": "elevated",
                "timestamp": h.promoted_at.isoformat(),
                "summary": f"Elevated: {h.source_environment} → {h.target_environment} (by {h.promoted_by})",
                "detail": {
                    "history_id": h.history_id,
                    "source_environment": h.source_environment,
                    "target_environment": h.target_environment,
                    "promoted_by": h.promoted_by,
                },
                "actor": h.promoted_by,
                "finding_id": None,
                "task_packet_id": None,
                "evaluation_id": None,
            })

    # 5. Audit events
    audit_stmt = select(ClientAuditEventRow).where(
        ClientAuditEventRow.project_id == project_id
    ).order_by(ClientAuditEventRow.created_at.desc()).limit(20)
    audit_events = list((await db.execute(audit_stmt)).scalars().all())
    for a in audit_events:
        ts = getattr(a, "timestamp", None) or a.created_at
        if ts:
            events.append({
                "event_id": f"audit_{a.event_id}",
                "event_type": a.event_type or "audit_event",
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "summary": f"{a.action or a.event_type}: {a.decision or ''}".strip(": "),
                "detail": {
                    "event_id": a.event_id,
                    "action": a.action,
                    "decision": a.decision,
                },
                "actor": a.source if hasattr(a, "source") else "system",
                "finding_id": None,
                "task_packet_id": None,
                "evaluation_id": None,
            })

    # Sort by timestamp descending and deduplicate
    seen_ids: set[str] = set()
    deduped: list[dict] = []
    for ev in sorted(events, key=lambda e: e["timestamp"], reverse=True):
        if ev["event_id"] not in seen_ids:
            seen_ids.add(ev["event_id"])
            deduped.append(ev)

    return deduped[:limit]
