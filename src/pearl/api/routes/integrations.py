"""Integration endpoint management and sync routes."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError, ValidationError
from pearl.repositories.integration_repo import (
    IntegrationEndpointRepository,
    IntegrationSyncLogRepository,
)
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Integrations"])


# --- Request/response models ---


class IntegrationEndpointCreate(BaseModel):
    name: str
    adapter_type: str
    integration_type: str  # "source", "sink", "bidirectional"
    category: str
    base_url: str
    auth_config: dict | None = None
    project_mapping: dict[str, str] | None = None
    enabled: bool = True
    labels: dict[str, str] | None = None


class IntegrationEndpointUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    auth_config: dict | None = None
    project_mapping: dict[str, str] | None = None
    enabled: bool | None = None
    labels: dict[str, str] | None = None


class PushEventRequest(BaseModel):
    event_type: str
    severity: str
    summary: str
    details: dict = Field(default_factory=dict)
    finding_ids: list[str] | None = None


# --- Helpers ---


async def _ensure_project_exists(project_id: str, db: AsyncSession):
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)
    return row


def _row_to_dict(row) -> dict:
    return {
        "endpoint_id": row.endpoint_id,
        "project_id": row.project_id,
        "name": row.name,
        "adapter_type": row.adapter_type,
        "integration_type": row.integration_type,
        "category": row.category,
        "base_url": row.base_url,
        "auth_config": row.auth_config,
        "project_mapping": row.project_mapping,
        "enabled": row.enabled,
        "labels": row.labels,
        "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
        "last_sync_status": row.last_sync_status,
    }


# --- Routes ---


@router.get("/projects/{project_id}/integrations", status_code=200)
async def list_integrations(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all configured integration endpoints for a project."""
    await _ensure_project_exists(project_id, db)
    repo = IntegrationEndpointRepository(db)
    rows = await repo.list_by_project(project_id)
    return [_row_to_dict(r) for r in rows]


@router.post("/projects/{project_id}/integrations", status_code=201)
async def register_integration(
    project_id: str,
    body: IntegrationEndpointCreate,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Register a new integration endpoint."""
    await _ensure_project_exists(project_id, db)
    repo = IntegrationEndpointRepository(db)

    # Check name uniqueness within project
    existing = await repo.get_by_name(project_id, body.name)
    if existing:
        raise ValidationError(
            f"Integration '{body.name}' already exists for this project",
            details={"endpoint_id": existing.endpoint_id},
        )

    endpoint_id = generate_id("intg_")
    row = await repo.create(
        endpoint_id=endpoint_id,
        project_id=project_id,
        name=body.name,
        adapter_type=body.adapter_type,
        integration_type=body.integration_type,
        category=body.category,
        base_url=body.base_url,
        auth_config=body.auth_config,
        project_mapping=body.project_mapping,
        enabled=body.enabled,
        labels=body.labels,
    )
    await db.commit()
    return _row_to_dict(row)


@router.put("/projects/{project_id}/integrations/{endpoint_id}", status_code=200)
async def update_integration(
    project_id: str,
    endpoint_id: str,
    body: IntegrationEndpointUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Update an integration endpoint's configuration."""
    repo = IntegrationEndpointRepository(db)
    row = await repo.get(endpoint_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("IntegrationEndpoint", endpoint_id)

    updates = {}
    for field in ("name", "base_url", "auth_config", "project_mapping", "enabled", "labels"):
        value = getattr(body, field)
        if value is not None:
            updates[field] = value

    if updates:
        await repo.update(row, **updates)
        await db.commit()

    return _row_to_dict(row)


@router.delete("/projects/{project_id}/integrations/{endpoint_id}", status_code=200)
async def disable_integration(
    project_id: str,
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Soft-delete: disables the integration endpoint."""
    repo = IntegrationEndpointRepository(db)
    row = await repo.get(endpoint_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("IntegrationEndpoint", endpoint_id)

    await repo.update(row, enabled=False)
    await db.commit()
    return {"endpoint_id": endpoint_id, "enabled": False}


@router.post(
    "/projects/{project_id}/integrations/{endpoint_id}/test",
    status_code=200,
)
async def test_integration(
    project_id: str,
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Test connectivity to an integration endpoint."""
    repo = IntegrationEndpointRepository(db)
    row = await repo.get(endpoint_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("IntegrationEndpoint", endpoint_id)

    # Build endpoint config from DB row
    from pearl.integrations.config import AuthConfig, IntegrationEndpoint, IntegrationRegistry
    from pearl.integrations.service import IntegrationService

    endpoint = IntegrationEndpoint(
        endpoint_id=row.endpoint_id,
        name=row.name,
        adapter_type=row.adapter_type,
        integration_type=row.integration_type,
        category=row.category,
        base_url=row.base_url,
        auth=AuthConfig(**(row.auth_config or {})),
        project_mapping=row.project_mapping,
        enabled=row.enabled,
        labels=row.labels,
    )

    registry = IntegrationRegistry(endpoints=[endpoint])
    service = IntegrationService(registry)
    result = await service.test_endpoint(endpoint_id)
    return result


@router.post(
    "/projects/{project_id}/integrations/{endpoint_id}/pull",
    status_code=200,
)
async def pull_from_integration(
    project_id: str,
    endpoint_id: str,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Trigger a pull from a source integration endpoint."""
    await _ensure_project_exists(project_id, db)
    repo = IntegrationEndpointRepository(db)
    row = await repo.get(endpoint_id)
    if not row or row.project_id != project_id:
        raise NotFoundError("IntegrationEndpoint", endpoint_id)

    if row.integration_type not in ("source", "bidirectional"):
        raise ValidationError(
            f"Endpoint '{row.name}' is a {row.integration_type}, not a source"
        )

    from pearl.integrations.config import AuthConfig, IntegrationEndpoint, IntegrationRegistry
    from pearl.integrations.service import IntegrationService

    endpoint = IntegrationEndpoint(
        endpoint_id=row.endpoint_id,
        name=row.name,
        adapter_type=row.adapter_type,
        integration_type=row.integration_type,
        category=row.category,
        base_url=row.base_url,
        auth=AuthConfig(**(row.auth_config or {})),
        project_mapping=row.project_mapping,
        enabled=row.enabled,
        labels=row.labels,
    )

    registry = IntegrationRegistry(endpoints=[endpoint])
    service = IntegrationService(registry)

    result = await service.pull_from_source(
        endpoint_id=endpoint_id,
        project_id=project_id,
        since=row.last_sync_at,
    )

    # Update last sync status
    now = datetime.now(timezone.utc)
    await repo.update(row, last_sync_at=now, last_sync_status="success")

    # Log the sync
    log_repo = IntegrationSyncLogRepository(db)
    await log_repo.create_log(
        log_id=generate_id("slog_"),
        endpoint_id=endpoint_id,
        project_id=project_id,
        direction="pull",
        status="success",
        records_processed=result.get("findings_count", 0),
    )

    await db.commit()

    return {
        "endpoint_id": endpoint_id,
        "endpoint_name": row.name,
        "findings_pulled": result.get("findings_count", 0),
        "synced_at": now.isoformat(),
    }
