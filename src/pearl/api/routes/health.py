"""Health check endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from pearl.config import settings

router = APIRouter()


@router.get("/server-config", include_in_schema=False)
async def server_config():
    """Return non-sensitive server flags needed by the frontend UI."""
    return {
        "reviewer_mode": settings.local_reviewer_mode,
        "local_mode": settings.local_mode,
    }


@router.get("/health")
async def health_check():
    """Return service health status (legacy)."""
    return {"status": "healthy", "service": "pearl-api", "version": "1.1.0"}


@router.get("/health/live")
async def liveness():
    """Kubernetes liveness probe — always returns 200 if process is running."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(request: Request):
    """Kubernetes readiness probe — checks DB and Redis connectivity."""
    checks: dict[str, str] = {}
    overall_ok = True

    # Check database
    try:
        session_factory = request.app.state.db_session_factory
        async with session_factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {exc}"
        overall_ok = False

    # Check Redis (optional — may be None in local mode)
    redis = getattr(request.app.state, "redis", None)
    if redis is not None:
        try:
            await redis.ping()
            checks["redis"] = "ok"
        except Exception as exc:
            checks["redis"] = f"error: {exc}"
            overall_ok = False
    else:
        checks["redis"] = "disabled"

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if overall_ok else "not_ready",
            "checks": checks,
        },
    )
