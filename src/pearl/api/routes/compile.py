"""Context compilation API routes."""

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.models.compiled_context import CompiledContextPackage
from pearl.repositories.compiled_package_repo import CompiledPackageRepository
from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
from pearl.repositories.org_baseline_repo import OrgBaselineRepository
from pearl.services.compiler.context_compiler import compile_context
from pearl.workers.queue import enqueue_job

router = APIRouter(tags=["ContextCompile"])


@router.post("/projects/{project_id}/compile-context", status_code=202)
async def compile_context_endpoint(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    body = await request.json()
    compile_options = body.get("compile_options", {})

    # For simplicity, run compilation synchronously but return 202 pattern
    # In production, this would enqueue to Redis and return immediately
    try:
        package = await compile_context(
            project_id=project_id,
            trace_id=trace_id,
            apply_exceptions=compile_options.get("apply_active_exceptions", True),
            session=db,
        )
        await db.commit()

        # Create a job record for tracking
        job = await enqueue_job(
            session=db,
            job_type="compile_context",
            project_id=project_id,
            trace_id=trace_id,
        )
        # Mark as already succeeded since we ran synchronously
        from pearl.repositories.job_repo import JobRepository
        from datetime import datetime, timezone
        job_repo = JobRepository(db)
        job_row = await job_repo.get(job.job_id)
        if job_row:
            job_row.status = "succeeded"
            job_row.result_refs = [{"ref_id": package.package_metadata.package_id,
                                   "kind": "artifact", "summary": "Compiled context package"}]
            job_row.updated_at = datetime.now(timezone.utc)
        await db.commit()

        return job.model_dump(mode="json", exclude_none=True)
    except Exception as e:
        # If compilation fails, still create a failed job
        job = await enqueue_job(
            session=db,
            job_type="compile_context",
            project_id=project_id,
            trace_id=trace_id,
        )
        from pearl.repositories.job_repo import JobRepository
        from datetime import datetime, timezone
        job_repo = JobRepository(db)
        job_row = await job_repo.get(job.job_id)
        if job_row:
            job_row.status = "failed"
            job_row.errors = [{"code": "COMPILE_ERROR", "message": str(e),
                              "trace_id": trace_id,
                              "timestamp": datetime.now(timezone.utc).isoformat()}]
            job_row.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise


@router.get("/projects/{project_id}/compiled-package")
async def get_compiled_package(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = CompiledPackageRepository(db)
    row = await repo.get_latest_by_project(project_id)
    if not row:
        raise NotFoundError("Compiled package", project_id)

    return row.package_data


@router.get("/projects/{project_id}/compiled-package/integrity")
async def get_package_integrity(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = CompiledPackageRepository(db)
    row = await repo.get_latest_by_project(project_id)
    if not row:
        return {"status": "missing", "package_id": None, "hash_valid": None,
                "source_drift": None, "drift_details": [], "compiled_at": None,
                "days_since_compiled": None}

    pkg_dict = row.package_data

    # 1. Tamper detection: recompute hash using the same detached-hash pattern
    stored_hash = pkg_dict.get("package_metadata", {}).get("integrity", {}).get("hash")
    compiled_at_str = pkg_dict.get("package_metadata", {}).get("integrity", {}).get("compiled_at")

    body_for_hash = json.loads(json.dumps(pkg_dict))  # deep copy
    body_for_hash["package_metadata"]["integrity"] = {"compiled_at": compiled_at_str}
    canonical = json.dumps(body_for_hash, sort_keys=True, separators=(",", ":"))
    computed_hash = hashlib.sha256(canonical.encode()).hexdigest()
    hash_valid = stored_hash is not None and stored_hash == computed_hash

    # 2. Governance drift detection
    snapshot = (pkg_dict.get("package_metadata", {})
                        .get("compiled_from", {})
                        .get("governance_snapshot"))
    drift_details: list[str] = []
    if snapshot:
        env_repo = EnvironmentProfileRepository(db)
        baseline_repo = OrgBaselineRepository(db)
        env_profile = await env_repo.get_by_project(project_id)
        baseline = await baseline_repo.get_by_project(project_id)

        if env_profile and baseline:
            current = {
                "autonomy_mode": env_profile.autonomy_mode,
                "allowed_actions": sorted(env_profile.allowed_capabilities or []),
                "blocked_actions": sorted(env_profile.blocked_capabilities or []),
                "approval_level": env_profile.approval_level,
                "risk_level": env_profile.risk_level,
                "prohibited_patterns": sorted(
                    baseline.defaults.get("coding", {}).get("prohibited_patterns", [])
                ),
                "secret_hardcoding_forbidden": baseline.defaults.get("coding", {}).get(
                    "secret_hardcoding_forbidden", False
                ),
                "wildcard_permissions_forbidden": baseline.defaults.get("iam", {}).get(
                    "wildcard_permissions_forbidden_by_default", False
                ),
            }
            for key, old_val in snapshot.items():
                new_val = current.get(key)
                if old_val != new_val:
                    drift_details.append(f"{key}: {old_val!r} → {new_val!r}")

    days_since = None
    if compiled_at_str:
        try:
            compiled_dt = datetime.fromisoformat(compiled_at_str.replace("Z", "+00:00"))
            days_since = (datetime.now(timezone.utc) - compiled_dt).days
        except (ValueError, AttributeError):
            pass

    status = "tampered" if not hash_valid else "stale" if drift_details else "current"

    return {
        "package_id": pkg_dict.get("package_metadata", {}).get("package_id"),
        "compiled_at": compiled_at_str,
        "status": status,
        "hash_valid": hash_valid,
        "source_drift": bool(drift_details),
        "drift_details": drift_details,
        "days_since_compiled": days_since,
    }
