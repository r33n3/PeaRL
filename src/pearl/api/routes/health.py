"""Health check endpoint."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health_check():
    """Return service health status."""
    return {"status": "healthy", "service": "pearl-api", "version": "1.1.0"}
