"""Local task packet generation — no DB, operates on in-memory CompiledContextPackage."""

from __future__ import annotations

from datetime import datetime, timezone

from pearl.models.common import Reference
from pearl.models.compiled_context import CompiledContextPackage
from pearl.models.task_packet import ContextBudget, TaskPacket
from pearl.services.id_generator import generate_id


def generate_task_packet_local(
    package: CompiledContextPackage,
    task_type: str,
    task_summary: str,
    trace_id: str,
    affected_components: list[str] | None = None,
    change_hints: list[str] | None = None,
    context_budget: dict | None = None,
) -> TaskPacket:
    """Generate a task-scoped context packet from a compiled package (no DB)."""
    autonomy = package.autonomy_policy
    allowed_actions = list(autonomy.allowed_actions)
    blocked_actions = list(autonomy.blocked_actions)

    relevant_controls = _filter_controls(package, affected_components)
    relevant_rai = _filter_rai_requirements(package, affected_components)
    required_tests = _determine_required_tests(package, task_type, affected_components)
    approval_triggers = _determine_approval_triggers(package, change_hints)
    evidence_required = _filter_evidence(package)
    reassessment_triggers = _extract_reassessment_triggers(package)

    budget = None
    if context_budget:
        budget = ContextBudget(
            max_tokens_hint=context_budget.get("max_tokens_hint"),
            deep_fetch_required=False,
        )

    packet_id = generate_id("tp_")
    package_id = package.package_metadata.package_id

    return TaskPacket(
        schema_version="1.1",
        task_packet_id=packet_id,
        project_id=package.project_identity.project_id,
        environment=package.project_identity.environment,
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


def _filter_controls(
    pkg: CompiledContextPackage, affected_components: list[str] | None
) -> list[str]:
    controls = list(pkg.security_requirements.required_controls)
    relevant = [c for c in controls if c in ("authz_checks", "audit_logging", "input_validation")]
    return relevant or controls[:3]


def _filter_rai_requirements(
    pkg: CompiledContextPackage, affected_components: list[str] | None
) -> list[str]:
    rai = pkg.responsible_ai_requirements
    if not rai:
        return []
    reqs: list[str] = []
    if rai.transparency and rai.transparency.model_provenance_logging_required:
        reqs.append("transparency.model_provenance_logging_required")
    return reqs


def _determine_required_tests(
    pkg: CompiledContextPackage, task_type: str, affected_components: list[str] | None
) -> list[str]:
    rt = pkg.required_tests
    if not rt:
        return ["token_validation_error_handling_tests"]
    result: list[str] = []
    if rt.security:
        result.append(rt.security[0])
    result.append("token_validation_error_handling_tests")
    return result


def _determine_approval_triggers(
    pkg: CompiledContextPackage, change_hints: list[str] | None
) -> list[str]:
    if not change_hints:
        return []
    checkpoints = pkg.approval_checkpoints or []
    triggers: list[str] = []
    for hint in change_hints:
        for cp in checkpoints:
            if cp.trigger == hint:
                triggers.append(hint)
    return triggers


def _filter_evidence(pkg: CompiledContextPackage) -> list[str]:
    evidence = pkg.evidence_requirements or []
    return evidence[:2] if evidence else ["decision_trace", "test_results"]


def _extract_reassessment_triggers(pkg: CompiledContextPackage) -> list[str]:
    ct = pkg.change_reassessment_triggers
    if not ct:
        return []
    delta = ct.architecture_delta or []
    return delta[:2] if delta else []
