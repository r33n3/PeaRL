"""Remediation spec generation API route."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import NotFoundError
from pearl.models.common import Reference
from pearl.models.remediation_spec import RemediationSpec, RiskSummary
from pearl.repositories.compiled_package_repo import CompiledPackageRepository
from pearl.repositories.finding_repo import FindingRepository
from pearl.repositories.remediation_spec_repo import RemediationSpecRepository
from pearl.services.compiler.integrity import compute_integrity
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Remediation"])


@router.post("/projects/{project_id}/remediation-specs/generate", status_code=201)
async def generate_remediation_spec(
    project_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    trace_id: str = Depends(get_trace_id),
) -> dict:
    body = await request.json()
    finding_refs = body["finding_refs"]
    environment = body["environment"]
    req_trace_id = body.get("trace_id", trace_id)

    # Load findings
    finding_repo = FindingRepository(db)
    findings = await finding_repo.get_by_ids(finding_refs)

    # Load compiled package for context
    pkg_repo = CompiledPackageRepository(db)
    pkg_row = await pkg_repo.get_latest_by_project(project_id)

    # Assess risk from findings
    max_severity = "low"
    severity_order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
    max_confidence = "low"
    confidence_order = {"low": 0, "medium": 1, "high": 2}

    for f in findings:
        if severity_order.get(f.severity, 0) > severity_order.get(max_severity, 0):
            max_severity = f.severity
        data = f.full_data or {}
        conf = data.get("confidence", "low")
        if confidence_order.get(conf, 0) > confidence_order.get(max_confidence, 0):
            max_confidence = conf

    # Classify the remediation based on finding characteristics
    is_sca_dep_fix = False
    touches_auth_flow = False
    for f in findings:
        data = f.full_data or {}
        source = f.source or {}
        tool_type = source.get("tool_type", "")
        control_refs = data.get("control_refs", [])
        if tool_type == "sca" and (f.fix_available or data.get("fix_available")):
            is_sca_dep_fix = True
        if "authz_checks" in control_refs or "auth_flow" in " ".join(control_refs):
            touches_auth_flow = True

    # Determine eligibility from compiled package rules + finding context
    base_eligibility = "human_required"
    if pkg_row:
        pkg = pkg_row.package_data
        rem_elig = pkg.get("autonomous_remediation_eligibility", {})
        base_eligibility = rem_elig.get("default", "human_required")

    # SCA dependency pin with fix available in non-prod → auto_allowed
    if is_sca_dep_fix and environment in ("dev", "pilot"):
        eligibility = "auto_allowed"
    elif touches_auth_flow or base_eligibility in ("auto_allowed_with_approval", "human_required"):
        eligibility = "auto_allowed_with_approval"
    else:
        eligibility = base_eligibility if base_eligibility != "human_required" else "auto_allowed_with_approval"

    # Determine approval requirements
    approval_required = eligibility in ("auto_allowed_with_approval", "human_required")
    approval_triggers = []
    if pkg_row:
        for cp in pkg_row.package_data.get("approval_checkpoints", []):
            if cp.get("trigger") in ("network_policy_changes", "auth_flow_change"):
                approval_triggers.append(cp["trigger"])

    # Generate finding-specific remediation content
    if is_sca_dep_fix:
        finding_titles = [f.title for f in findings]
        cve_ids = [f.cve_id for f in findings if f.cve_id]
        required_outcome = (
            f"Update pinned dependency to patched version that resolves "
            f"{', '.join(cve_ids) if cve_ids else 'the known vulnerability'}. "
            f"Verify no breaking changes in updated package."
        )
        impl_constraints = [
            "Pin to exact patched version, not a range",
            "Run full test suite after dependency update",
            "Verify no new vulnerabilities introduced by updated version",
        ]
        required_tests = ["dependency_resolution_test", "integration_regression_test"]
        evidence_required = ["before_after_lockfile_diff", "test_results"]
        if not approval_required:
            evidence_required.append("ci_pipeline_pass")
    elif touches_auth_flow:
        required_outcome = (
            "Implement proper authentication and authorization checks at the identified "
            "trust boundary. Ensure all callers are verified before granting access."
        )
        impl_constraints = [
            "Must not break existing authenticated workflows",
            "Add integration tests covering the new auth checks",
            "Follow existing auth patterns in the codebase",
        ]
        required_tests = ["auth_boundary_test", "integration_regression_test"]
        evidence_required = ["before_after_code_diff", "test_results", "approval_records"]
    else:
        required_outcome = (
            "Remove undeclared public egress and constrain outbound traffic "
            "to declared allowlist destinations."
        )
        impl_constraints = [
            "Do not broaden egress during remediation",
            "Preserve telemetry.internal and llm-gateway.internal connectivity",
        ]
        required_tests = ["network_policy_regression_test", "egress_allowlist_validation_test"]
        evidence_required = ["before_after_network_policy_diff", "test_results", "approval_records"]

    if touches_auth_flow and "auth_flow_change" not in approval_triggers:
        approval_triggers.append("auth_flow_change")

    spec_id = generate_id("rs_")
    spec = RemediationSpec(
        schema_version="1.1",
        remediation_spec_id=spec_id,
        project_id=project_id,
        environment=environment,
        finding_refs=finding_refs,
        risk_summary=RiskSummary(
            risk_level=max_severity,
            business_impact=max_severity,
            confidence=max_confidence,
        ),
        eligibility=eligibility,
        required_outcome=required_outcome,
        implementation_constraints=impl_constraints,
        required_tests=required_tests,
        evidence_required=evidence_required,
        approval_required=approval_required,
        approval_triggers=approval_triggers or ["network_policy_changes"],
        trace_id=req_trace_id,
        generated_at=datetime.now(timezone.utc),
        integrity=compute_integrity({"spec_id": spec_id, "project_id": project_id}),
        references=[Reference(ref_id=ref, kind="finding", summary="Source finding") for ref in finding_refs],
    )

    # Store
    spec_repo = RemediationSpecRepository(db)
    await spec_repo.create(
        remediation_spec_id=spec_id,
        project_id=project_id,
        environment=environment,
        spec_data=spec.model_dump(mode="json", exclude_none=True),
        trace_id=req_trace_id,
    )
    await db.commit()

    return spec.model_dump(mode="json", exclude_none=True)
