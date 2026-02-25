"""Background scheduler for periodic scan target polling."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

logger = logging.getLogger(__name__)

# Frequency label → timedelta
_FREQUENCY_MAP = {
    "hourly": timedelta(hours=1),
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
}

# Scheduler interval in seconds
_POLL_INTERVAL = 60


async def _schedule_due_scans(session_factory, redis) -> int:
    """Check all active scan targets and enqueue overdue ones. Returns enqueue count."""
    from pearl.db.models.scan_target import ScanTargetRow
    from pearl.workers.queue import enqueue_job

    now = datetime.now(timezone.utc)
    enqueued = 0

    async with session_factory() as session:
        stmt = select(ScanTargetRow).where(
            ScanTargetRow.status == "active",
            ScanTargetRow.scan_frequency != "on_demand",
        )
        result = await session.execute(stmt)
        targets = list(result.scalars().all())

        for target in targets:
            freq_delta = _FREQUENCY_MAP.get(target.scan_frequency)
            if not freq_delta:
                continue

            # Check if scan is overdue
            if target.last_scanned_at is None:
                due = True
            else:
                next_due = target.last_scanned_at + freq_delta
                due = now >= next_due

            if not due:
                continue

            # Distributed lock via Redis SET NX to prevent duplicate scheduling
            lock_key = f"pearl:scheduler:lock:{target.scan_target_id}"
            if redis:
                locked = await redis.set(lock_key, "1", nx=True, ex=int(freq_delta.total_seconds()))
                if not locked:
                    logger.debug("Scan target %s already locked by another instance", target.scan_target_id)
                    continue

            try:
                job = await enqueue_job(
                    session=session,
                    job_type="scan_source",
                    project_id=target.project_id,
                    trace_id=f"scheduler_{target.scan_target_id}",
                    payload={
                        "project_id": target.project_id,
                        "scan_target_id": target.scan_target_id,
                        "environment": (target.environment_scope or ["dev"])[0],
                    },
                    redis=redis,
                )
                enqueued += 1
                logger.info(
                    "Scheduled scan for target %s (project=%s, job=%s)",
                    target.scan_target_id, target.project_id, job.job_id,
                )
            except Exception as exc:
                logger.warning("Failed to enqueue scan for target %s: %s", target.scan_target_id, exc)

        await session.commit()

    return enqueued


async def run_scheduler(app) -> None:
    """Background task that periodically enqueues overdue scan jobs."""
    logger.info("Scan scheduler started (poll_interval=%ds)", _POLL_INTERVAL)

    while True:
        try:
            await asyncio.sleep(_POLL_INTERVAL)

            session_factory = getattr(app.state, "db_session_factory", None)
            redis = getattr(app.state, "redis", None)

            if not session_factory:
                continue

            count = await _schedule_due_scans(session_factory, redis)
            if count:
                logger.info("Scheduler enqueued %d scan jobs", count)

        except asyncio.CancelledError:
            logger.info("Scan scheduler stopped")
            break
        except Exception as exc:
            logger.exception("Scheduler error: %s", exc)
            # Continue running despite errors
