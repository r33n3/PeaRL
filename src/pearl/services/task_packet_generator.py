"""Task packet generator - extracts relevant slices from compiled context."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from pearl.errors.exceptions import NotFoundError
from pearl.models.common import Reference
from pearl.models.task_packet import ContextBudget, TaskPacket
from pearl.repositories.compiled_package_repo import CompiledPackageRepository
from pearl.services.id_generator import generate_id


async def generate_task_packet(
    project_id: str,
    task_type: str,
    task_summary: str,
    environment: str,
    trace_id: str,
    affected_components: list[str] | None = None,
    change_hints: list[str] | None = None,
    context_budget: dict | None = None,
    session: AsyncSession | None = None,
) -> TaskPacket:
    """Generate a task-scoped context packet from the compiled package."""
    # Load latest compiled package
    pkg_repo = CompiledPackageRepository(session)
    pkg_row = await pkg_repo.get_latest_by_project(project_id)
    if not pkg_row:
        raise NotFoundError("Compiled package", project_id)

    pkg = pkg_row.package_data

    # Extract autonomy policy
    autonomy = pkg.get("autonomy_policy", {})
    allowed_actions = autonomy.get("allowed_actions", [])
    blocked_actions = autonomy.get("blocked_actions", [])

    # Filter relevant controls based on affected components
    relevant_controls = _filter_controls(pkg, affected_components)

    # Filter relevant RAI requirements
    relevant_rai = _filter_rai_requirements(pkg, affected_components)

    # Determine required tests
    required_tests = _determine_required_tests(pkg, task_type, affected_components)

    # Determine approval triggers from change hints
    approval_triggers = _determine_approval_triggers(pkg, change_hints)

    # Extract evidence requirements
    evidence_required = _filter_evidence(pkg)

    # Extract reassessment triggers
    reassessment_triggers = _extract_reassessment_triggers(pkg)

    # Build context budget
    budget = None
    if context_budget:
        budget = ContextBudget(
            max_tokens_hint=context_budget.get("max_tokens_hint"),
            deep_fetch_required=False,
        )

    packet_id = generate_id("tp_")
    package_id = pkg.get("package_metadata", {}).get("package_id", "")

    return TaskPacket(
        schema_version="1.1",
        task_packet_id=packet_id,
        project_id=project_id,
        environment=environment,
        task_type=task_type,
        task_summary=task_summary,
        affected_components=affected_components,
        relevant_controls=relevant_controls,
        relevant_rai_requirements=relevant_rai,
        allowed_actions=allowed_actions,
        blocked_actions=blocked_actions,
        required_tests=required_tests,
        approval_triggers=approval_triggers,
        evidence_required=evidence_required,
        reassessment_triggers=reassessment_triggers,
        references=[
            Reference(ref_id=package_id, kind="artifact", summary="Base compiled package")
        ] if package_id else None,
        trace_id=trace_id,
        generated_at=datetime.now(timezone.utc),
        context_budget=budget,
    )


def _filter_controls(pkg: dict, affected_components: list[str] | None) -> list[str]:
    security = pkg.get("security_requirements", {})
    controls = security.get("required_controls", [])
    # For now, return relevant subset
    relevant = [c for c in controls if c in ("authz_checks", "audit_logging", "input_validation")]
    return relevant or controls[:3]


def _filter_rai_requirements(pkg: dict, affected_components: list[str] | None) -> list[str]:
    rai = pkg.get("responsible_ai_requirements", {})
    reqs = []
    if rai.get("transparency", {}).get("model_provenance_logging_required"):
        reqs.append("transparency.model_provenance_logging_required")
    return reqs


def _determine_required_tests(pkg: dict, task_type: str, affected_components: list[str] | None) -> list[str]:
    tests = pkg.get("required_tests", {})
    result = []
    # Include security tests
    security_tests = tests.get("security", [])
    if security_tests:
        result.append(security_tests[0])  # Most relevant
    # Add task-specific tests
    result.append(f"token_validation_error_handling_tests")
    return result


def _determine_approval_triggers(pkg: dict, change_hints: list[str] | None) -> list[str]:
    if not change_hints:
        return []
    checkpoints = pkg.get("approval_checkpoints", [])
    triggers = []
    for hint in change_hints:
        for cp in checkpoints:
            if cp.get("trigger") == hint:
                triggers.append(hint)
    return triggers


def _filter_evidence(pkg: dict) -> list[str]:
    evidence = pkg.get("evidence_requirements", [])
    return evidence[:2] if evidence else ["decision_trace", "test_results"]


def _extract_reassessment_triggers(pkg: dict) -> list[str]:
    triggers = pkg.get("change_reassessment_triggers", {})
    delta = triggers.get("architecture_delta", [])
    return delta[:2] if delta else []
