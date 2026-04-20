"""Materializer service for factory run summaries.

Aggregates ClientCostEntryRow data for a factory run (session_id == frun_id)
into a single FactoryRunSummaryRow via idempotent upsert.

This service is model-free — no LLM calls, deterministic computation only.
The caller is responsible for session.commit().
"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.governance_telemetry import ClientCostEntryRow
from pearl.db.models.workload import WorkloadRow
from pearl.db.models.finding import FindingRow
from pearl.db.models.promotion import PromotionHistoryRow
from pearl.repositories.factory_run_summary_repo import FactoryRunSummaryRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.task_packet_repo import TaskPacketRepository

logger = structlog.get_logger(__name__)


async def materialize_run(
    *,
    frun_id: str,
    task_packet_id: str | None,
    project_id: str,
    session: AsyncSession,
    svid: str | None = None,
) -> str | None:
    """Aggregate cost entries and context into a FactoryRunSummaryRow.

    Steps (in order):
    1. Aggregate ClientCostEntryRow where session_id == frun_id
    2. Early exit if no entries and no task_packet_id
    3. Resolve svid from workload if not supplied
    4. Resolve goal_id from project
    5. Derive outcome from task packet
    6. Collect anomaly flags from open drift findings
    7. Check for recent promotion
    8. Upsert the summary row (no commit — caller commits)

    Returns frun_id on success, None if nothing to materialize.
    """

    # ── 1. Aggregate cost entries ─────────────────────────────────────────
    stmt = select(ClientCostEntryRow).where(ClientCostEntryRow.session_id == frun_id)
    result = await session.execute(stmt)
    entries = list(result.scalars().all())

    total_cost_usd: float = sum(e.cost_usd for e in entries)
    models_used: list[str] = sorted(set(e.model for e in entries if e.model))
    tools_called: list[str] = sorted(
        set(tool for e in entries for tool in (e.tools_called or []))
    )

    duration_values = [e.duration_ms for e in entries if e.duration_ms is not None]
    duration_ms: int | None = sum(duration_values) if duration_values else None

    started_at = min(e.timestamp for e in entries) if entries else None
    completed_at = max(e.timestamp for e in entries) if entries else None
    environment: str = entries[0].environment if entries else "sandbox"

    # ── 2. Early exit guard ───────────────────────────────────────────────
    if not entries and not task_packet_id:
        return None

    # ── 3. Resolve svid from workload (best-effort) ───────────────────────
    if not svid and task_packet_id:
        try:
            wl_stmt = (
                select(WorkloadRow)
                .where(WorkloadRow.task_packet_id == task_packet_id)
                .limit(1)
            )
            wl_result = await session.execute(wl_stmt)
            wl = wl_result.scalar_one_or_none()
            if wl is not None:
                svid = wl.svid
        except Exception as exc:  # noqa: BLE001
            logger.warning("materialize_run: svid lookup failed", frun_id=frun_id, error=str(exc))

    # ── 4. Resolve goal_id from project (best-effort) ─────────────────────
    goal_id: str | None = None
    try:
        project = await ProjectRepository(session).get(project_id)
        if project is not None:
            goal_id = project.goal_id
    except Exception as exc:  # noqa: BLE001
        logger.warning("materialize_run: goal_id lookup failed", frun_id=frun_id, error=str(exc))

    # ── 5. Derive outcome from task packet ────────────────────────────────
    outcome: str = "abandoned"
    if task_packet_id:
        try:
            packet = await TaskPacketRepository(session).get(task_packet_id)
            if packet is not None:
                pkt_outcome = (packet.outcome or {}).get("status")
                if pkt_outcome == "completed":
                    outcome = "achieved"
                elif pkt_outcome == "failed":
                    outcome = "failed"
                elif packet.execution_phase == "complete":
                    outcome = "achieved"
                elif packet.execution_phase == "failed":
                    outcome = "failed"
                else:
                    outcome = "abandoned"
        except Exception as exc:  # noqa: BLE001
            logger.warning("materialize_run: outcome lookup failed", frun_id=frun_id, error=str(exc))
            outcome = "abandoned"

    # ── 6. Anomaly flags from open drift findings (best-effort) ──────────
    anomaly_flags: list[str] = []
    try:
        drift_categories = ("drift_acute", "drift_trend", "behavioral_drift")
        findings_stmt = select(FindingRow).where(
            FindingRow.project_id == project_id,
            FindingRow.category.in_(drift_categories),
            FindingRow.status == "open",
        )
        findings_result = await session.execute(findings_stmt)
        findings = list(findings_result.scalars().all())
        anomaly_flags = [
            f"{f.anomaly_code or f.category}:{f.title[:100]}" for f in findings
        ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("materialize_run: anomaly flags lookup failed", frun_id=frun_id, error=str(exc))

    # ── 7. Promotion check (best-effort) ─────────────────────────────────
    promoted: bool = False
    promotion_env: str | None = None
    try:
        promo_stmt = (
            select(PromotionHistoryRow)
            .where(PromotionHistoryRow.project_id == project_id)
            .order_by(PromotionHistoryRow.promoted_at.desc())
            .limit(1)
        )
        promo_result = await session.execute(promo_stmt)
        promo_row = promo_result.scalar_one_or_none()
        if promo_row is not None:
            promoted = True
            promotion_env = promo_row.target_environment
    except Exception as exc:  # noqa: BLE001
        logger.warning("materialize_run: promotion check failed", frun_id=frun_id, error=str(exc))

    # ── 8. Upsert — caller commits ────────────────────────────────────────
    await FactoryRunSummaryRepository(session).upsert(
        {
            "frun_id": frun_id,
            "project_id": project_id,
            "task_packet_id": task_packet_id,
            "goal_id": goal_id,
            "svid": svid,
            "environment": environment,
            "outcome": outcome,
            "total_cost_usd": total_cost_usd,
            "models_used": models_used,
            "tools_called": tools_called,
            "duration_ms": duration_ms,
            "anomaly_flags": anomaly_flags,
            "promoted": promoted,
            "promotion_env": promotion_env,
            "started_at": started_at,
            "completed_at": completed_at,
        }
    )

    return frun_id
