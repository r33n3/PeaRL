"""Admin-only endpoints for destructive project operations."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.project import ProjectRow
from pearl.dependencies import RequireAdmin, get_db
from pearl.errors.exceptions import NotFoundError, ValidationError
from pearl.repositories.project_repo import ProjectRepository

router = APIRouter(tags=["Admin"])


class BulkDeleteRequest(BaseModel):
    confirm: bool = False


async def _delete_project_data(session: AsyncSession, project_id: str) -> int:
    """Delete all data for a single project in FK-safe order. Returns table count."""
    # 1. integration_sync_logs (indirect via endpoint_id)
    await session.execute(
        text(
            "DELETE FROM integration_sync_logs WHERE endpoint_id IN "
            "(SELECT endpoint_id FROM integration_endpoints WHERE project_id = :pid)"
        ),
        {"pid": project_id},
    )
    # 2. integration_endpoints
    await session.execute(
        text("DELETE FROM integration_endpoints WHERE project_id = :pid"),
        {"pid": project_id},
    )
    # 3. fairness / context tables
    for table in (
        "fairness_cases",
        "fairness_requirements_specs",
        "evidence_packages",
        "fairness_exceptions",
        "monitoring_signals",
        "context_contracts",
        "context_packs",
        "context_receipts",
    ):
        await session.execute(
            text(f"DELETE FROM {table} WHERE project_id = :pid"),  # noqa: S608
            {"pid": project_id},
        )
    # 4. compiled / environment tables
    for table in (
        "compiled_packages",
        "environment_profiles",
        "app_specs",
        "org_baselines",
    ):
        await session.execute(
            text(f"DELETE FROM {table} WHERE project_id = :pid"),  # noqa: S608
            {"pid": project_id},
        )
    # 5. notifications, scan_targets
    for table in ("notifications", "scan_targets"):
        await session.execute(
            text(f"DELETE FROM {table} WHERE project_id = :pid"),  # noqa: S608
            {"pid": project_id},
        )
    # 6. promotion tables
    for table in (
        "promotion_pipelines",
        "promotion_evaluations",
        "promotion_history",
        "promotion_gates",
    ):
        await session.execute(
            text(f"DELETE FROM {table} WHERE project_id = :pid"),  # noqa: S608
            {"pid": project_id},
        )
    # 7. reports, remediation_specs, exception_records, task_packets
    for table in ("reports", "remediation_specs", "exception_records", "task_packets"):
        await session.execute(
            text(f"DELETE FROM {table} WHERE project_id = :pid"),  # noqa: S608
            {"pid": project_id},
        )
    # 8. approval child rows, finding resolutions, then parents
    await session.execute(
        text(
            "DELETE FROM approval_comments WHERE approval_request_id IN "
            "(SELECT approval_request_id FROM approval_requests WHERE project_id = :pid)"
        ),
        {"pid": project_id},
    )
    await session.execute(
        text(
            "DELETE FROM approval_decisions WHERE approval_request_id IN "
            "(SELECT approval_request_id FROM approval_requests WHERE project_id = :pid)"
        ),
        {"pid": project_id},
    )
    await session.execute(
        text(
            "DELETE FROM finding_resolutions WHERE finding_id IN "
            "(SELECT finding_id FROM findings WHERE project_id = :pid)"
        ),
        {"pid": project_id},
    )
    for table in ("approval_requests", "findings", "jobs"):
        await session.execute(
            text(f"DELETE FROM {table} WHERE project_id = :pid"),  # noqa: S608
            {"pid": project_id},
        )
    # 9. telemetry
    for table in ("client_audit_events", "client_cost_entries"):
        await session.execute(
            text(f"DELETE FROM {table} WHERE project_id = :pid"),  # noqa: S608
            {"pid": project_id},
        )
    # 10. projects
    await session.execute(
        text("DELETE FROM projects WHERE project_id = :pid"),
        {"pid": project_id},
    )
    return 19


async def _delete_all_project_data(session: AsyncSession) -> int:
    """Delete all project data across the system. Returns table count."""
    # 1. integration_sync_logs
    await session.execute(text("DELETE FROM integration_sync_logs"))
    # 2. integration_endpoints
    await session.execute(text("DELETE FROM integration_endpoints"))
    # 3. fairness / context tables
    for table in (
        "fairness_cases",
        "fairness_requirements_specs",
        "evidence_packages",
        "fairness_exceptions",
        "monitoring_signals",
        "context_contracts",
        "context_packs",
        "context_receipts",
    ):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    # 4. compiled / environment tables
    for table in (
        "compiled_packages",
        "environment_profiles",
        "app_specs",
        "org_baselines",
    ):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    # 5. notifications, scan_targets
    for table in ("notifications", "scan_targets"):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    # 6. promotion tables
    for table in (
        "promotion_pipelines",
        "promotion_evaluations",
        "promotion_history",
        "promotion_gates",
    ):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    # 7. reports, remediation_specs, exception_records, task_packets
    for table in ("reports", "remediation_specs", "exception_records", "task_packets"):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    # 8. approval child rows, finding resolutions, then parents
    for table in ("approval_comments", "approval_decisions", "finding_resolutions"):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    for table in ("approval_requests", "findings", "jobs"):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    # 9. telemetry
    for table in ("client_audit_events", "client_cost_entries"):
        await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
    # 10. projects
    await session.execute(text("DELETE FROM projects"))
    return 19


@router.delete("/admin/projects/{project_id}", dependencies=[RequireAdmin])
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete one project and all its dependent data (admin only)."""
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    tables_affected = await _delete_project_data(db, project_id)
    await db.commit()
    return {"deleted": project_id, "tables_affected": tables_affected}


@router.delete("/admin/projects", dependencies=[RequireAdmin])
async def delete_all_projects(
    body: BulkDeleteRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Wipe every project and all dependent data (admin only). Requires confirm=true."""
    if not body.confirm:
        raise ValidationError("confirm must be true to delete all projects")

    count_result = await db.execute(select(func.count()).select_from(ProjectRow))
    deleted_count = count_result.scalar_one()

    tables_cleared = await _delete_all_project_data(db)
    await db.commit()
    return {"deleted_count": deleted_count, "tables_cleared": tables_cleared}
