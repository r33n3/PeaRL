"""Auto-demotion service — triggered by critical ACoP anomalies (BA-02, BA-05, BA-06).

ACoP §5.4, §9.4: critical BA codes or repeated rate limit violations trigger automatic
demotion, logged immutably in promotion_history.
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.repositories.finding_repo import FindingRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.repositories.promotion_repo import PromotionHistoryRepository
from pearl.services.id_generator import generate_id

# BA codes that trigger automatic demotion
_CRITICAL_BA_CODES = {"BA-02", "BA-05", "BA-06"}


async def auto_demote(
    *,
    session: AsyncSession,
    project_id: str,
    anomaly_code: str,
    triggered_by: str,
    from_environment: str | None = None,
    redis=None,
) -> dict | None:
    """Record an automatic demotion for a critical anomaly.

    Returns the history record dict on success, or None if the anomaly code is
    not critical. Does NOT commit — caller is responsible for session.commit().
    """
    if anomaly_code not in _CRITICAL_BA_CODES:
        return None

    now = datetime.now(timezone.utc)
    history_id = generate_id("hist_")

    # Determine source environment: prefer explicit arg, fall back to ProjectRow field
    source_env = from_environment
    if not source_env:
        proj_repo = ProjectRepository(session)
        project = await proj_repo.get(project_id)
        source_env = (project.current_environment if project else None) or "unknown"

    history_repo = PromotionHistoryRepository(session)
    await history_repo.create(
        history_id=history_id,
        project_id=project_id,
        source_environment=source_env,
        target_environment="rollback",
        evaluation_id="auto_demotion",
        promoted_by="pearl-auto-demotion",
        promoted_at=now,
        details={
            "type": "auto_demotion",
            "triggered_by": triggered_by,
            "anomaly_code": anomaly_code,
            "reason": f"Automatic demotion: critical ACoP anomaly {anomaly_code} detected",
        },
    )

    # Update current_environment on ProjectRow to reflect demotion
    proj_repo = ProjectRepository(session)
    project = await proj_repo.get(project_id)
    if project:
        await proj_repo.update(project, current_environment="rollback")

    # Emit SSE event if Redis is available
    if redis:
        try:
            from pearl.api.routes.stream import publish_event
            await publish_event(redis, "auto_demotion", {
                "project_id": project_id,
                "history_id": history_id,
                "anomaly_code": anomaly_code,
                "from_environment": source_env,
                "triggered_by": triggered_by,
                "demoted_at": now.isoformat(),
            })
        except Exception:
            pass  # SSE failure must not block the demotion record

    return {
        "history_id": history_id,
        "project_id": project_id,
        "type": "auto_demotion",
        "anomaly_code": anomaly_code,
        "from_environment": source_env,
        "triggered_by": triggered_by,
        "demoted_at": now.isoformat(),
    }
