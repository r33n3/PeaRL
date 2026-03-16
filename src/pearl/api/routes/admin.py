"""Admin-only endpoints for destructive project operations."""

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.project import ProjectRow
from pearl.dependencies import RequireAdmin, get_db
from pearl.errors.exceptions import NotFoundError, ValidationError
from pearl.repositories.fairness_repo import AuditEventRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Admin"])

# Exhaustive whitelist of tables that may be cleared by project-scoped deletes.
# Adding a table here is a deliberate, reviewed action — never interpolate from
# user-supplied input.
_PROJECT_TABLES: frozenset[str] = frozenset({
    "fairness_cases", "fairness_requirements_specs", "evidence_packages",
    "fairness_exceptions", "monitoring_signals", "context_contracts",
    "context_packs", "context_receipts", "compiled_packages",
    "environment_profiles", "app_specs", "org_baselines", "notifications",
    "scan_targets", "promotion_pipelines", "promotion_evaluations",
    "promotion_history", "promotion_gates", "reports", "remediation_specs",
    "exception_records", "task_packets", "approval_comments",
    "approval_decisions", "finding_resolutions", "approval_requests",
    "findings", "jobs", "client_audit_events", "client_cost_entries",
})


class BulkDeleteRequest(BaseModel):
    confirm: bool = False


def _checked_table(name: str) -> str:
    """Return table name only if it is in the whitelist — raises otherwise."""
    if name not in _PROJECT_TABLES:
        raise ValueError(f"Table '{name}' is not in the admin delete whitelist")
    return name


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
            text(f"DELETE FROM {_checked_table(table)} WHERE project_id = :pid"),
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
            text(f"DELETE FROM {_checked_table(table)} WHERE project_id = :pid"),
            {"pid": project_id},
        )
    # 5. notifications, scan_targets
    for table in ("notifications", "scan_targets"):
        await session.execute(
            text(f"DELETE FROM {_checked_table(table)} WHERE project_id = :pid"),
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
            text(f"DELETE FROM {_checked_table(table)} WHERE project_id = :pid"),
            {"pid": project_id},
        )
    # 7. reports, remediation_specs, exception_records, task_packets
    for table in ("reports", "remediation_specs", "exception_records", "task_packets"):
        await session.execute(
            text(f"DELETE FROM {_checked_table(table)} WHERE project_id = :pid"),
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
            text(f"DELETE FROM {_checked_table(table)} WHERE project_id = :pid"),
            {"pid": project_id},
        )
    # 9. telemetry
    for table in ("client_audit_events", "client_cost_entries"):
        await session.execute(
            text(f"DELETE FROM {_checked_table(table)} WHERE project_id = :pid"),
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
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    # 4. compiled / environment tables
    for table in (
        "compiled_packages",
        "environment_profiles",
        "app_specs",
        "org_baselines",
    ):
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    # 5. notifications, scan_targets
    for table in ("notifications", "scan_targets"):
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    # 6. promotion tables
    for table in (
        "promotion_pipelines",
        "promotion_evaluations",
        "promotion_history",
        "promotion_gates",
    ):
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    # 7. reports, remediation_specs, exception_records, task_packets
    for table in ("reports", "remediation_specs", "exception_records", "task_packets"):
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    # 8. approval child rows, finding resolutions, then parents
    for table in ("approval_comments", "approval_decisions", "finding_resolutions"):
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    for table in ("approval_requests", "findings", "jobs"):
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    # 9. telemetry
    for table in ("client_audit_events", "client_cost_entries"):
        await session.execute(text(f"DELETE FROM {_checked_table(table)}"))
    # 10. projects
    await session.execute(text("DELETE FROM projects"))
    return 19


@router.delete("/admin/projects/{project_id}", dependencies=[RequireAdmin])
async def delete_project(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete one project and all its dependent data (admin only)."""
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    tables_affected = await _delete_project_data(db, project_id)
    actor = getattr(request.state, "user", {}).get("sub")
    await AuditEventRepository(db).append(
        event_id=generate_id("evt_"),
        resource_id=project_id,
        action_type="project.deleted",
        actor=actor,
        details={"tables_affected": tables_affected},
    )
    await db.commit()
    return {"deleted": project_id, "tables_affected": tables_affected}


@router.delete("/admin/projects", dependencies=[RequireAdmin])
async def delete_all_projects(
    body: BulkDeleteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Wipe every project and all dependent data (admin only). Requires confirm=true."""
    if not body.confirm:
        raise ValidationError("confirm must be true to delete all projects")

    count_result = await db.execute(select(func.count()).select_from(ProjectRow))
    deleted_count = count_result.scalar_one()

    tables_cleared = await _delete_all_project_data(db)
    actor = getattr(request.state, "user", {}).get("sub")
    await AuditEventRepository(db).append(
        event_id=generate_id("evt_"),
        resource_id="system",
        action_type="project.bulk_deleted",
        actor=actor,
        details={"deleted_count": deleted_count},
    )
    await db.commit()
    return {"deleted_count": deleted_count, "tables_cleared": tables_cleared}
