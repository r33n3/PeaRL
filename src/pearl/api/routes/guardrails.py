"""Guardrails API routes — list, get details, get recommendations."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import NotFoundError
from pearl.repositories.project_repo import ProjectRepository
from pearl.scanning.policy.guardrails import Guardrail, get_default_guardrails
from pearl.scanning.types import GuardrailType

router = APIRouter(tags=["Guardrails"])

_registry = get_default_guardrails()


@router.get("/guardrails", status_code=200)
async def list_guardrails(
    category: str | None = Query(None, description="Filter by guardrail type category"),
    severity: str | None = Query(None, description="Filter by severity"),
) -> list[dict]:
    """List all guardrails with optional filtering."""
    if category:
        try:
            gt = GuardrailType(category)
            guardrails = _registry.get_by_type(gt)
        except ValueError:
            guardrails = []
    elif severity:
        guardrails = _registry.get_by_severity(severity)
    else:
        guardrails = _registry.get_all()

    return [
        {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "category": g.guardrail_type.value,
            "severity": g.severity.value,
            "implementation_steps": g.implementation_steps,
        }
        for g in guardrails
    ]


@router.get("/guardrails/{guardrail_id}", status_code=200)
async def get_guardrail(guardrail_id: str) -> dict:
    """Get guardrail detail with code examples."""
    guardrail = _registry.get(guardrail_id)
    if not guardrail:
        raise NotFoundError("Guardrail", guardrail_id)

    return {
        "id": guardrail.id,
        "name": guardrail.name,
        "description": guardrail.description,
        "category": guardrail.guardrail_type.value,
        "severity": guardrail.severity.value,
        "implementation_steps": guardrail.implementation_steps,
        "code_examples": guardrail.code_examples,
        "mitigates_categories": [c.value for c in guardrail.mitigates_categories],
    }


def _to_bedrock_config(guardrail: Guardrail) -> dict:
    """Generate an AWS Bedrock CreateGuardrail-compatible config fragment."""
    config = {"name": guardrail.name, "description": guardrail.description}

    cat = guardrail.guardrail_type.value

    if cat == "input_validation":
        config["topicPolicyConfig"] = {
            "topicsConfig": [{
                "name": "prompt_injection",
                "definition": "Attempts to override system instructions or manipulate model behavior",
                "examples": ["Ignore previous instructions", "You are now DAN"],
                "type": "DENY"
            }]
        }
    elif cat == "content_moderation":
        config["contentPolicyConfig"] = {
            "filtersConfig": [
                {"type": "SEXUAL", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "VIOLENCE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "HATE", "inputStrength": "HIGH", "outputStrength": "HIGH"},
                {"type": "INSULTS", "inputStrength": "MEDIUM", "outputStrength": "HIGH"},
            ]
        }
    elif cat == "output_filtering":
        config["sensitiveInformationPolicyConfig"] = {
            "piiEntitiesConfig": [
                {"type": "EMAIL", "action": "ANONYMIZE"},
                {"type": "PHONE", "action": "ANONYMIZE"},
                {"type": "NAME", "action": "ANONYMIZE"},
                {"type": "SSN", "action": "BLOCK"},
                {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
                {"type": "AWS_ACCESS_KEY", "action": "BLOCK"},
            ]
        }
    elif cat == "rate_limiting":
        config["note"] = "Bedrock does not natively support rate limiting — implement via API Gateway throttling"

    return config


def _to_cedar_policy(guardrail: Guardrail, project_id: str) -> dict:
    """Generate a Cedar policy fragment for this guardrail."""
    cat = guardrail.guardrail_type.value
    action_ns = "AgentCore::Action"

    if cat == "input_validation":
        return {
            "policy_id": f"pearl_guardrail_{guardrail.id}_{project_id}",
            "type": "forbid",
            "statement": (
                f'forbid(\n'
                f'  principal,\n'
                f'  action == {action_ns}::"ExecuteApiCall",\n'
                f'  resource\n'
                f') when {{\n'
                f'  !(context has input_validated) ||\n'
                f'  context.input_validated == false\n'
                f'}};'
            ),
            "description": f"Enforce {guardrail.name} — block API calls without validated input"
        }
    elif cat == "content_moderation":
        return {
            "policy_id": f"pearl_guardrail_{guardrail.id}_{project_id}",
            "type": "forbid",
            "statement": (
                f'forbid(\n'
                f'  principal,\n'
                f'  action == {action_ns}::"InvokeFoundationModel",\n'
                f'  resource\n'
                f') when {{\n'
                f'  !(context has content_moderation_enabled) ||\n'
                f'  context.content_moderation_enabled == false\n'
                f'}};'
            ),
            "description": f"Enforce {guardrail.name} — require content moderation on model calls"
        }
    elif cat == "output_filtering":
        return {
            "policy_id": f"pearl_guardrail_{guardrail.id}_{project_id}",
            "type": "forbid",
            "statement": (
                f'forbid(\n'
                f'  principal,\n'
                f'  action == {action_ns}::"InvokeFoundationModel",\n'
                f'  resource\n'
                f') when {{\n'
                f'  !(context has pii_filter_active) ||\n'
                f'  context.pii_filter_active == false\n'
                f'}};'
            ),
            "description": f"Enforce {guardrail.name} — require PII filtering on all model responses"
        }
    else:
        return {
            "policy_id": f"pearl_guardrail_{guardrail.id}_{project_id}",
            "type": "forbid",
            "statement": (
                f'forbid(\n'
                f'  principal,\n'
                f'  action == {action_ns}::"ExecuteApiCall",\n'
                f'  resource\n'
                f') when {{\n'
                f'  !(context has guardrails_active)\n'
                f'}};'
            ),
            "description": f"Enforce {guardrail.name}"
        }


@router.get("/projects/{project_id}/recommended-guardrails", status_code=200)
async def get_recommended_guardrails(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get guardrails recommended for a project based on its findings."""
    from sqlalchemy import select
    from pearl.db.models.finding import FindingRow
    from pearl.db.models.app_spec import AppSpecRow
    from pearl.scanning.service import ScanningService
    from pearl.scanning.analyzers.base import AnalyzerFinding
    from pearl.scanning.types import ScanSeverity, AttackCategory, ComponentType

    repo = ProjectRepository(db)
    project = await repo.get(project_id)
    if not project:
        raise NotFoundError("Project", project_id)

    # ── Determine project type ────────────────────────────────────────────────
    # Check for agentcore_alias_id directly on the model first
    is_agent = bool(getattr(project, "agentcore_alias_id", None))

    # Fallback: check app_spec for architecture.agent_type
    if not is_agent:
        app_spec_stmt = (
            select(AppSpecRow)
            .where(AppSpecRow.project_id == project_id)
            .limit(1)
        )
        app_spec_result = await db.execute(app_spec_stmt)
        app_spec_row = app_spec_result.scalars().first()
        if app_spec_row and app_spec_row.full_spec:
            arch = app_spec_row.full_spec.get("architecture", {})
            agent_type = arch.get("agent_type", "")
            if agent_type:
                is_agent = True

    # Also check project tags for "agent" marker
    if not is_agent and project.tags:
        is_agent = "agent" in (project.tags or [])

    ai_app = project.ai_enabled and not is_agent

    # ── Load open findings ────────────────────────────────────────────────────
    stmt = (
        select(FindingRow)
        .where(FindingRow.project_id == project_id)
        .where(FindingRow.status == "open")
    )
    result = await db.execute(stmt)
    findings = list(result.scalars().all())

    # Convert to AnalyzerFinding-like objects for the service
    analyzer_findings = []
    for f in findings:
        try:
            analyzer_findings.append(AnalyzerFinding(
                title=f.title,
                description=f.full_data.get("description", "") if f.full_data else "",
                severity=ScanSeverity.MEDIUM,
                category=AttackCategory.PROMPT_INJECTION,
                component_type=ComponentType.CODE,
                component_name="",
            ))
        except Exception:
            pass

    service = ScanningService()
    recommended = service.recommend_guardrails(analyzer_findings)

    # ── Build per-guardrail response entries ──────────────────────────────────
    guardrail_entries = []
    for g in recommended:
        entry: dict = {
            "id": g.id,
            "name": g.name,
            "description": g.description,
            "category": g.guardrail_type.value,
            "severity": g.severity.value,
            "implementation_steps": g.implementation_steps,
            "code_examples": g.code_examples,
        }
        if ai_app:
            entry["bedrock_config"] = _to_bedrock_config(g)
        if is_agent:
            entry["cedar_policy"] = _to_cedar_policy(g, project_id)
        guardrail_entries.append(entry)

    # ── Determine project_type and target_platforms ───────────────────────────
    if is_agent:
        project_type = "agent"
    elif project.ai_enabled:
        project_type = "ai_application"
    else:
        project_type = "standard"

    target_platforms = (["bedrock"] if ai_app else []) + (["cedar", "agentcore"] if is_agent else [])

    return {
        "project_id": project_id,
        "project_type": project_type,
        "target_platforms": target_platforms,
        "open_findings_count": len(findings),
        "recommended_guardrails": guardrail_entries,
    }
