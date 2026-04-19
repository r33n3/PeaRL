"""Project CRUD API routes."""

from datetime import datetime, timezone

import json
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

import re

from pydantic import BaseModel as PydanticBaseModel

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import ConflictError, NotFoundError, ValidationError
from pearl.models.common import TraceabilityRef
from pearl.models.enums import BusinessCriticality, ExternalExposure
from pearl.models.project import Project
from pearl.repositories.environment_profile_repo import EnvironmentProfileRepository
from pearl.repositories.project_repo import ProjectRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Projects"])


class RegisterProjectRequest(PydanticBaseModel):
    name: str
    owner_team: str
    business_criticality: BusinessCriticality = BusinessCriticality.LOW
    external_exposure: ExternalExposure = ExternalExposure.PUBLIC
    ai_enabled: bool = True
    description: str | None = None
    bu_id: str | None = None


@router.post("/projects/register", status_code=201)
async def register_project(
    body: RegisterProjectRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Register a new project with minimal input.

    Derives project_id from the name, creates the project, and returns
    the ready-to-use .pearl.yaml content so the caller can write it to disk.
    No .pearl.yaml needs to exist first.
    """
    from pearl.config import settings

    # Derive project_id slug from name
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:48]
    project_id = f"proj_{slug}"

    repo = ProjectRepository(db)

    # Handle slug collision with a short suffix
    if await repo.get(project_id):
        import random
        import string
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        project_id = f"proj_{slug}-{suffix}"

    await repo.create(
        project_id=project_id,
        name=body.name,
        description=body.description,
        owner_team=body.owner_team,
        business_criticality=body.business_criticality,
        external_exposure=body.external_exposure,
        ai_enabled=body.ai_enabled,
        schema_version="1.1",
        bu_id=body.bu_id,
    )

    env_repo = EnvironmentProfileRepository(db)
    await env_repo.create(
        profile_id=generate_id("envprof_"),
        project_id=project_id,
        environment="sandbox",
        delivery_stage="bootstrap",
        risk_level="low",
        autonomy_mode="assistive",
    )

    await db.commit()

    api_url = settings.effective_public_api_url
    description_line = f"description: {body.description}" if body.description else "# description: optional"
    bu_line = f"bu_id: {body.bu_id}" if body.bu_id else "# bu_id: optional"

    pearl_yaml = f"""# PeaRL governance configuration
# Drop this file in your project root and open the folder in Claude Code.

project_id: {project_id}
api_url: {api_url}

name: {body.name}
owner_team: {body.owner_team}
business_criticality: {body.business_criticality.value}
external_exposure: {body.external_exposure.value}
ai_enabled: {str(body.ai_enabled).lower()}
{description_line}
{bu_line}

environments:
  sandbox: sandbox
  dev: dev
  preprod: preprod
  main: prod

protected_branches:
  - dev
  - preprod
  - main
"""

    return {
        "project_id": project_id,
        "name": body.name,
        "pearl_yaml": pearl_yaml,
        "next_step": "Write the 'pearl_yaml' content to .pearl.yaml in the project root.",
    }


@router.post("/projects/bootstrap", status_code=201)
async def bootstrap_project(
    body: RegisterProjectRequest,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    """Full one-shot bootstrap: create project + minimal app spec + compile context.

    Returns pearl_yaml, pearl_dev_toml, and compiled_package ready to write to disk.
    After writing these three files, all local MCP tools work immediately.
    No prior setup needed — no .pearl.yaml, no .pearl/ directory required.
    """
    import json as _json
    from pearl.config import settings
    from pearl.models.app_spec import ApplicationSpec, AppIdentity, Architecture, ArchComponent
    from pearl.repositories.app_spec_repo import AppSpecRepository
    from pearl.services.compiler.context_compiler import compile_context

    # 1. Derive project_id
    slug = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:48]
    project_id = f"proj_{slug}"

    repo = ProjectRepository(db)
    existing = await repo.get(project_id)
    if existing:
        # Idempotent — re-bootstrap an already-registered project
        project_id = existing.project_id
    else:
        if await repo.get(project_id):
            import random, string
            suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
            project_id = f"proj_{slug}-{suffix}"

        await repo.create(
            project_id=project_id,
            name=body.name,
            description=body.description,
            owner_team=body.owner_team,
            business_criticality=body.business_criticality,
            external_exposure=body.external_exposure,
            ai_enabled=body.ai_enabled,
            schema_version="1.1",
            bu_id=body.bu_id,
        )

        env_repo = EnvironmentProfileRepository(db)
        await env_repo.create(
            profile_id=generate_id("envprof_"),
            project_id=project_id,
            environment="sandbox",
            delivery_stage="bootstrap",
            risk_level="low",
            autonomy_mode="assistive",
        )

    # 2. Upsert minimal app spec so context compilation has something to work with
    spec = ApplicationSpec(
        schema_version="1.1",
        kind="PearlApplicationSpec",
        application=AppIdentity(
            app_id=project_id,
            owner_team=body.owner_team,
            business_criticality=body.business_criticality,
            external_exposure=body.external_exposure,
            ai_enabled=body.ai_enabled,
        ),
        architecture=Architecture(
            components=[ArchComponent(id="app", type="application", criticality="low")]
        ),
    )
    app_spec_repo = AppSpecRepository(db)
    full_spec = spec.model_dump(mode="json", exclude_none=True)
    existing_spec = await app_spec_repo.get_by_project(project_id)
    if existing_spec:
        await app_spec_repo.update(existing_spec, app_id=project_id, full_spec=full_spec, integrity=None)
    else:
        await app_spec_repo.create(
            app_id=project_id,
            project_id=project_id,
            full_spec=full_spec,
            integrity=None,
            schema_version="1.1",
        )

    await db.commit()

    # 3. Compile context synchronously
    package = await compile_context(
        project_id=project_id,
        trace_id=trace_id,
        apply_exceptions=True,
        session=db,
    )
    await db.commit()

    # 4. Build the compiled package JSON (strip integrity_hash — local tools don't need it)
    from pearl.repositories.compiled_package_repo import CompiledPackageRepository
    pkg_repo = CompiledPackageRepository(db)
    pkg_row = await pkg_repo.get_latest_by_project(project_id)
    compiled_package_dict = dict(pkg_row.package_data) if pkg_row else package.model_dump(mode="json", exclude_none=True)
    compiled_package_dict.pop("integrity_hash", None)

    api_url = settings.effective_public_api_url
    description_line = f"description: {body.description}" if body.description else "# description: optional"
    bu_line = f"bu_id: {body.bu_id}" if body.bu_id else "# bu_id: optional"

    pearl_yaml = f"""# PeaRL governance configuration
# Drop this file in your project root and open the folder in Claude Code.

project_id: {project_id}
api_url: {api_url}

name: {body.name}
owner_team: {body.owner_team}
business_criticality: {body.business_criticality.value}
external_exposure: {body.external_exposure.value}
ai_enabled: {str(body.ai_enabled).lower()}
{description_line}
{bu_line}

environments:
  sandbox: sandbox
  dev: dev
  preprod: preprod
  main: prod

protected_branches:
  - dev
  - preprod
  - main
"""

    pearl_dev_toml = f"""[pearl-dev]
project_id = "{project_id}"
environment = "sandbox"
api_url = "{api_url}"
package_path = ".pearl/compiled-context-package.json"
audit_path = ".pearl/audit.jsonl"
approvals_dir = ".pearl/approvals"
auto_task_context = true
"""

    # 5. Auto-provision downstream integrations (SonarQube, etc.)
    integrations_provisioned: list[dict] = []
    next_steps = [
        "Write 'pearl_yaml' to .pearl.yaml in the project root",
        "Write 'pearl_dev_toml' to .pearl/pearl-dev.toml",
        "Write 'compiled_package' as JSON to .pearl/compiled-context-package.json",
    ]

    try:
        from pearl.repositories.integration_repo import IntegrationEndpointRepository
        from pearl.integrations.config import AuthConfig, IntegrationEndpoint as IntgEndpoint
        from pearl.integrations.adapters.sonarqube import SonarQubeAdapter
        from pearl.services.id_generator import generate_id as _gen_id

        intg_repo = IntegrationEndpointRepository(db)
        sonar_row = await intg_repo.get_org_by_adapter_type("sonarqube")

        if sonar_row and sonar_row.enabled:
            sonar_endpoint = IntgEndpoint(
                endpoint_id=sonar_row.endpoint_id,
                name=sonar_row.name,
                adapter_type=sonar_row.adapter_type,
                integration_type=sonar_row.integration_type,
                category=sonar_row.category,
                base_url=sonar_row.base_url,
                auth=AuthConfig(**(sonar_row.auth_config or {})),
                labels=sonar_row.labels,
            )
            adapter = SonarQubeAdapter()
            sonar_key = re.sub(r"[^a-z0-9_\-.:]+", "-", project_id.replace("proj_", ""))
            provision = await adapter.provision_project(sonar_endpoint, sonar_key, body.name)

            # Register a project-level integration pointing at this SonarQube project
            existing_proj_intg = await intg_repo.get_by_name(project_id, "SonarQube")
            if not existing_proj_intg:
                await intg_repo.create(
                    endpoint_id=_gen_id("intg_"),
                    project_id=project_id,
                    name="SonarQube",
                    adapter_type="sonarqube",
                    integration_type="source",
                    category="sast",
                    base_url=sonar_row.base_url,
                    auth_config=sonar_row.auth_config,
                    labels={"project_keys": sonar_key},
                )
                await db.commit()

            integrations_provisioned.append({
                "tool": "sonarqube",
                "project_key": provision["project_key"],
                "scanner_command": provision["scanner_command"],
                "already_existed": provision["already_existed"],
            })
            next_steps.append(
                f"Run sonar-scanner to populate findings:\n  {provision['scanner_command']}"
            )
    except Exception as _exc:
        import logging as _log
        _log.getLogger(__name__).warning("Integration auto-provisioning skipped: %s", _exc)

    return {
        "project_id": project_id,
        "name": body.name,
        "pearl_yaml": pearl_yaml,
        "pearl_dev_toml": pearl_dev_toml,
        "compiled_package": compiled_package_dict,
        "integrations_provisioned": integrations_provisioned,
        "next_steps": next_steps,
    }


@router.post("/projects/{project_id}/provision-integrations", status_code=200)
async def provision_project_integrations(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Provision downstream integrations (SonarQube, etc.) for an existing project.

    Idempotent — safe to call multiple times. Creates the SonarQube project if it
    doesn't exist, rotates the analysis token, and returns the ready-to-run
    sonar-scanner command.
    """
    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    results: list[dict] = []

    from pearl.repositories.integration_repo import IntegrationEndpointRepository
    from pearl.integrations.config import AuthConfig, IntegrationEndpoint as IntgEndpoint
    from pearl.integrations.adapters.sonarqube import SonarQubeAdapter

    intg_repo = IntegrationEndpointRepository(db)
    sonar_row = await intg_repo.get_org_by_adapter_type("sonarqube")

    if sonar_row and sonar_row.enabled:
        sonar_endpoint = IntgEndpoint(
            endpoint_id=sonar_row.endpoint_id,
            name=sonar_row.name,
            adapter_type=sonar_row.adapter_type,
            integration_type=sonar_row.integration_type,
            category=sonar_row.category,
            base_url=sonar_row.base_url,
            auth=AuthConfig(**(sonar_row.auth_config or {})),
            labels=sonar_row.labels,
        )
        adapter = SonarQubeAdapter()
        sonar_key = re.sub(r"[^a-z0-9_\-.:]+", "-", project_id.replace("proj_", ""))
        provision = await adapter.provision_project(sonar_endpoint, sonar_key, project.name)

        existing_proj_intg = await intg_repo.get_by_name(project_id, "SonarQube")
        if not existing_proj_intg:
            await intg_repo.create(
                endpoint_id=generate_id("intg_"),
                project_id=project_id,
                name="SonarQube",
                adapter_type="sonarqube",
                integration_type="source",
                category="sast",
                base_url=sonar_row.base_url,
                auth_config=sonar_row.auth_config,
                labels={"project_keys": sonar_key},
            )
        await db.commit()

        results.append({
            "tool": "sonarqube",
            "project_key": provision["project_key"],
            "scanner_command": provision["scanner_command"],
            "already_existed": provision["already_existed"],
        })

    return {
        "project_id": project_id,
        "integrations_provisioned": results,
        "message": "Run the scanner_command to populate findings." if results else "No integrations configured at org level.",
    }


@router.post("/projects", status_code=201)
async def create_project(
    project: Project,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    repo = ProjectRepository(db)

    # Check for duplicate
    existing = await repo.get(project.project_id)
    if existing:
        raise ConflictError(f"Project '{project.project_id}' already exists")

    now = datetime.now(timezone.utc)
    project.created_at = now
    project.updated_at = now
    project.traceability = TraceabilityRef(trace_id=trace_id, source_refs=["api:/projects"])

    await repo.create(
        project_id=project.project_id,
        name=project.name,
        description=project.description,
        owner_team=project.owner_team,
        business_criticality=project.business_criticality,
        external_exposure=project.external_exposure,
        ai_enabled=project.ai_enabled,
        schema_version=project.schema_version,
        bu_id=project.bu_id,
    )

    env_repo = EnvironmentProfileRepository(db)
    await env_repo.create(
        profile_id=generate_id("envprof_"),
        project_id=project.project_id,
        environment="sandbox",
        delivery_stage="bootstrap",
        risk_level="low",
        autonomy_mode="assistive",
    )

    await db.commit()
    return project.model_dump(mode="json", exclude_none=True)


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    return {
        **Project(
            schema_version=row.schema_version,
            project_id=row.project_id,
            name=row.name,
            description=row.description,
            owner_team=row.owner_team,
            business_criticality=row.business_criticality,
            external_exposure=row.external_exposure,
            ai_enabled=row.ai_enabled,
            bu_id=row.bu_id,
            tags=getattr(row, "tags", None),
            created_at=row.created_at,
            updated_at=row.updated_at,
        ).model_dump(mode="json", exclude_none=True),
        "current_environment": row.current_environment or "sandbox",
        # ── Governance container fields ──
        "intake_card_id": row.intake_card_id,
        "goal_id": row.goal_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "risk_classification": row.risk_classification,
        "agent_members": row.agent_members,
        "litellm_key_refs": row.litellm_key_refs,
        "memory_policy_refs": row.memory_policy_refs,
        "qualification_packet_id": row.qualification_packet_id,
    }


@router.put("/projects/{project_id}")
async def update_project(
    project_id: str,
    project: Project,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    now = datetime.now(timezone.utc)
    await repo.update(
        row,
        name=project.name,
        description=project.description,
        owner_team=project.owner_team,
        business_criticality=project.business_criticality,
        external_exposure=project.external_exposure,
        ai_enabled=project.ai_enabled,
    )
    row.updated_at = now
    await db.commit()

    return Project(
        schema_version=row.schema_version,
        project_id=row.project_id,
        name=row.name,
        description=row.description,
        owner_team=row.owner_team,
        business_criticality=row.business_criticality,
        external_exposure=row.external_exposure,
        ai_enabled=row.ai_enabled,
        created_at=row.created_at,
        updated_at=now,
    ).model_dump(mode="json", exclude_none=True)


@router.patch("/projects/{project_id}/bu")
async def assign_project_to_bu(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Assign (or unassign) a project to a business unit."""
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    bu_id = body.get("bu_id")  # None = unassign
    row.bu_id = bu_id
    await db.commit()
    return {"project_id": project_id, "bu_id": bu_id}


@router.patch("/projects/{project_id}/tags")
async def update_project_tags(
    project_id: str,
    body: dict,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Set the tags list for a project (replaces existing tags)."""
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    tags = body.get("tags", [])
    if not isinstance(tags, list):
        raise ValidationError("tags must be a list of strings")
    row.tags = [str(t) for t in tags]
    await db.commit()
    return {"project_id": project_id, "tags": row.tags}


@router.get("/projects/{project_id}/pearl.yaml", response_class=PlainTextResponse)
async def get_pearl_yaml(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Download a ready-to-use .pearl.yaml config file for this project."""
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    from pearl.config import settings

    description_line = f"description: {row.description}" if row.description else "# description: optional"
    bu_line = f"bu_id: {row.bu_id}" if row.bu_id else "# bu_id: optional — assign to a business unit"
    ai_enabled = str(row.ai_enabled).lower()

    content = f"""# PeaRL governance configuration
# Drop this file in your project root and open the folder in Claude Code.
# Claude Code will auto-register this project on the first prompt.

project_id: {row.project_id}
api_url: {settings.effective_public_api_url}

# Registration fields — used for auto-registration if project is not yet in PeaRL
name: {row.name}
owner_team: {row.owner_team}
business_criticality: {row.business_criticality}
external_exposure: {row.external_exposure}
ai_enabled: {ai_enabled}
{description_line}
{bu_line}

# Branch → environment mapping
environments:
  sandbox: sandbox
  dev: dev
  preprod: preprod
  main: prod

# Branch protection targets (gates enforced on PRs to these branches)
protected_branches:
  - dev
  - preprod
  - main
"""
    return content


@router.get("/projects/{project_id}/mcp.json", response_class=PlainTextResponse)
async def get_mcp_json(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> str:
    """Download a ready-to-use .mcp.json that wires the PeaRL MCP server into Claude Code."""
    from pearl.config import settings

    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    # Resolve the pearl_dev src path — prefer explicit config, fall back to auto-detect
    if settings.pearl_src_path:
        src_path = settings.pearl_src_path
    else:
        # src/pearl/api/routes/projects.py → go up 4 levels to reach src/
        src_path = str(Path(__file__).resolve().parents[3])

    api_url = settings.effective_public_api_url

    mcp_config = {
        "mcpServers": {
            "pearl": {
                "command": "python",
                "args": [
                    "-m", "pearl_dev.unified_mcp",
                    "--directory", ".",
                    "--api-url", api_url,
                ],
                "env": {
                    "PYTHONPATH": src_path,
                },
            }
        }
    }
    return json.dumps(mcp_config, indent=2) + "\n"


@router.get("/projects/{project_id}/summary")
async def get_project_summary(
    project_id: str,
    format: str = Query("markdown", pattern="^(markdown|json)$"),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get a project governance summary in markdown or JSON."""
    from pearl.repositories.finding_repo import FindingRepository
    from pearl.repositories.promotion_repo import PromotionEvaluationRepository
    from pearl.repositories.fairness_repo import (
        EvidencePackageRepository,
        FairnessCaseRepository,
        FairnessExceptionRepository,
        FairnessRequirementsSpecRepository,
        MonitoringSignalRepository,
    )
    from pearl.services.markdown_renderer import render_project_summary

    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    project_data = {
        "project_id": row.project_id,
        "name": row.name,
        "description": row.description,
        "owner_team": row.owner_team,
        "business_criticality": row.business_criticality,
        "external_exposure": row.external_exposure,
        "ai_enabled": row.ai_enabled,
    }

    # Findings by severity
    finding_repo = FindingRepository(db)
    all_findings = await finding_repo.list_by_field("project_id", project_id)
    findings_by_severity: dict[str, int] = {}
    for f in all_findings:
        sev = f.severity or "unknown"
        findings_by_severity[sev] = findings_by_severity.get(sev, 0) + 1

    # Promotion readiness
    promotion = None
    try:
        eval_repo = PromotionEvaluationRepository(db)
        latest = await eval_repo.get_latest_by_project(project_id)
        if latest:
            promotion = {
                "source_environment": latest.source_environment,
                "target_environment": latest.target_environment,
                "status": latest.status,
                "passed_count": latest.passed_count,
                "failed_count": latest.failed_count,
                "total_count": latest.total_count,
                "progress_pct": latest.progress_pct,
                "blockers": latest.blockers,
                "rule_results": latest.rule_results,
                "evaluated_at": latest.evaluated_at.isoformat() if latest.evaluated_at else None,
            }
    except Exception:
        pass

    # Fairness posture
    fairness = None
    if row.ai_enabled:
        try:
            fc_repo = FairnessCaseRepository(db)
            fc = await fc_repo.get_by_project(project_id)
            frs_repo = FairnessRequirementsSpecRepository(db)
            frs = await frs_repo.get_by_project(project_id)
            ev_repo = EvidencePackageRepository(db)
            ev_list = await ev_repo.list_by_project(project_id)
            exc_repo = FairnessExceptionRepository(db)
            exc_list = await exc_repo.get_active_by_project(project_id)

            fairness = {}
            if fc:
                fairness["fairness_case"] = {
                    "fc_id": fc.fc_id,
                    "risk_tier": fc.risk_tier,
                    "fairness_criticality": fc.fairness_criticality,
                }
            if frs:
                fairness["requirements"] = frs.requirements or []
            if ev_list:
                latest_ev = ev_list[0]
                fairness["evidence"] = {
                    "evidence_id": latest_ev.evidence_id,
                    "attestation_status": latest_ev.attestation_status,
                }
            if exc_list:
                fairness["exceptions"] = [
                    {"exception_id": e.exception_id, "reason": (e.compensating_controls or {}).get("reason", ""), "status": e.status}
                    for e in exc_list
                ]
        except Exception:
            pass

    if format == "markdown":
        md = render_project_summary(
            project=project_data,
            findings_by_severity=findings_by_severity if findings_by_severity else None,
            promotion=promotion,
            fairness=fairness,
        )
        return {"format": "markdown", "content": md}

    return {
        "format": "json",
        "project": project_data,
        "findings_by_severity": findings_by_severity,
        "promotion_readiness": promotion,
        "fairness": fairness,
    }


# Governance block text — written to CLAUDE.md during project onboarding
PEARL_GOVERNANCE_BLOCK = """
---
## PeaRL Governance

All environment promotions and elevation requests **must go through PeaRL**.

- Verify `./pearl/` symlink exists before any elevation action
- Use PeaRL MCP tools (`pearl_check_action`, `pearl_request_approval`) — never bypass or self-approve a gate
- If a gate blocks you, call `pearl_request_approval` and stop
- `PEARL_LOCAL=1` and similar bypass flags must never be set
- No shutting down, restarting, or modifying the PeaRL backend from within this project
"""


@router.post("/projects/{project_id}/confirm-claude-md", status_code=200)
async def confirm_claude_md(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Confirm that the PeaRL governance block has been written to CLAUDE.md.

    Call this after writing the governance block returned in this response
    to the project's CLAUDE.md. Sets claude_md_verified=True on the project,
    which satisfies the CLAUDE_MD_GOVERNANCE_PRESENT gate rule.
    """
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    row.claude_md_verified = True
    await db.commit()

    return {
        "project_id": project_id,
        "claude_md_verified": True,
        "governance_block": PEARL_GOVERNANCE_BLOCK.strip(),
        "message": "Governance block confirmed. Gate rule CLAUDE_MD_GOVERNANCE_PRESENT will now pass.",
    }


class RegisterAgentsRequest(PydanticBaseModel):
    coordinator: str | None = None
    workers: list[str] = []
    evaluators: list[str] = []
    litellm_key_refs: list[str] = []
    memory_policy_refs: list[str] = []
    goal_id: str | None = None
    intake_card_id: str | None = None
    target_type: str | None = None
    target_id: str | None = None
    risk_classification: str | None = None
    qualification_packet_id: str | None = None


@router.post("/projects/{project_id}/agents")
async def register_project_agents(
    project_id: str,
    body: RegisterAgentsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """WTK registers coordinator, worker, and evaluator agents against a project."""
    user = getattr(request.state, "user", {})
    if not any(r in user.get("roles", []) for r in ("admin", "operator", "service_account")):
        from pearl.errors.exceptions import AuthorizationError
        raise AuthorizationError("operator, admin, or service_account role required")

    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    agent_members = {
        "coordinator": body.coordinator,
        "workers": body.workers,
        "evaluators": body.evaluators,
    }
    row = await repo.update_governance_fields(
        project_id=project_id,
        agent_members=agent_members,
        litellm_key_refs=body.litellm_key_refs or None,
        memory_policy_refs=body.memory_policy_refs or None,
        goal_id=body.goal_id,
        intake_card_id=body.intake_card_id,
        target_type=body.target_type,
        target_id=body.target_id,
        risk_classification=body.risk_classification,
        qualification_packet_id=body.qualification_packet_id,
    )
    await db.commit()
    await db.refresh(row)
    return {
        "project_id": row.project_id,
        "agent_members": row.agent_members,
        "litellm_key_refs": row.litellm_key_refs,
        "memory_policy_refs": row.memory_policy_refs,
        "goal_id": row.goal_id,
        "intake_card_id": row.intake_card_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "risk_classification": row.risk_classification,
        "qualification_packet_id": row.qualification_packet_id,
    }


@router.get("/projects/{project_id}/governance-state")
async def get_project_governance_state(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return the full governance container state for a project.

    Used by WTK to check gate status and by the PeaRL reviewer UI.
    """
    repo = ProjectRepository(db)
    row = await repo.get(project_id)
    if not row:
        raise NotFoundError("Project", project_id)

    from pearl.repositories.approval_repo import ApprovalRequestRepository
    approval_repo = ApprovalRequestRepository(db)
    pending = await approval_repo.list_by_project(project_id)
    pending_list = [
        {
            "approval_request_id": a.approval_request_id,
            "request_type": a.request_type,
            "status": a.status,
            "environment": a.environment,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in pending
        if a.status in ("pending", "needs_info")
    ]

    from pearl.repositories.compiled_package_repo import CompiledPackageRepository
    pkg_repo = CompiledPackageRepository(db)
    pkg = await pkg_repo.get_latest_by_project(project_id)
    gate_status = None
    if pkg:
        pkg_data = pkg.package_data or {}
        gate_status = {
            "package_id": pkg.package_id,
            "compiled_at": pkg_data.get("package_metadata", {}).get("integrity", {}).get("compiled_at"),
            "environment": pkg_data.get("project_identity", {}).get("environment"),
        }

    return {
        "project_id": row.project_id,
        "name": row.name,
        "current_environment": row.current_environment,
        "intake_card_id": row.intake_card_id,
        "goal_id": row.goal_id,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "risk_classification": row.risk_classification,
        "agent_members": row.agent_members,
        "litellm_key_refs": row.litellm_key_refs,
        "memory_policy_refs": row.memory_policy_refs,
        "qualification_packet_id": row.qualification_packet_id,
        "pending_approvals": pending_list,
        "pending_approvals_count": len(pending_list),
        "gate_status": gate_status,
    }
