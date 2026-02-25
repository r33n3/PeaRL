"""Round-trip tests for all entity Pydantic models against example payloads."""

import json
from pathlib import Path

import pytest

SPEC_DIR = Path(__file__).resolve().parents[1] / "PeaRL_spec"
EXAMPLES_DIR = SPEC_DIR / "examples"


def load_example(rel_path: str) -> dict:
    return json.loads((EXAMPLES_DIR / rel_path).read_text(encoding="utf-8"))


class TestProjectModel:
    def test_create_request_roundtrip(self):
        from pearl.models.project import Project
        data = load_example("project/create-project.request.json")
        model = Project.model_validate(data)
        assert model.project_id == "proj_customer_support_ai"
        assert model.ai_enabled is True
        dumped = model.model_dump(mode="json", exclude_none=True)
        for key in data:
            assert dumped[key] == data[key]

    def test_create_response_roundtrip(self):
        from pearl.models.project import Project
        data = load_example("project/create-project.response.json")
        model = Project.model_validate(data)
        assert model.traceability is not None
        assert model.traceability.trace_id == "trc_proj_create_001"


class TestOrgBaselineModel:
    def test_request_roundtrip(self):
        from pearl.models.org_baseline import OrgBaseline
        data = load_example("project/org-baseline.request.json")
        model = OrgBaseline.model_validate(data)
        assert model.kind == "PearlOrgBaseline"
        assert model.baseline_id == "orgb_secure_autonomous_v1"
        assert model.defaults.coding.secure_coding_standard_required is True
        dumped = model.model_dump(mode="json", exclude_none=True)
        assert dumped["defaults"]["coding"] == data["defaults"]["coding"]


class TestAppSpecModel:
    def test_request_roundtrip(self):
        from pearl.models.app_spec import ApplicationSpec
        data = load_example("project/app-spec.request.json")
        model = ApplicationSpec.model_validate(data)
        assert model.kind == "PearlApplicationSpec"
        assert model.application.app_id == "customer-support-ai-assistant"
        assert len(model.architecture.components) == 4
        assert len(model.architecture.trust_boundaries) == 3


class TestEnvironmentProfileModel:
    def test_request_roundtrip(self):
        from pearl.models.environment_profile import EnvironmentProfile
        data = load_example("project/environment-profile.request.json")
        model = EnvironmentProfile.model_validate(data)
        assert model.profile_id == "envp_preprod_supervised_high"
        assert model.environment == "preprod"
        assert model.autonomy_mode == "supervised_autonomous"
        assert model.approval_level == "high"


class TestCompiledContextPackageModel:
    def test_response_roundtrip(self):
        from pearl.models.compiled_context import CompiledContextPackage
        data = load_example("compile/compiled-package.response.json")
        model = CompiledContextPackage.model_validate(data)
        assert model.kind == "PearlCompiledContextPackage"
        assert model.package_metadata.package_id == "pkg_customer_support_ai_preprod_001"
        assert model.autonomy_policy.mode == "supervised_autonomous"
        assert len(model.security_requirements.required_controls) == 5
        assert model.responsible_ai_requirements.transparency.ai_disclosure_required is True
        assert model.network_requirements.public_egress_forbidden is True
        assert len(model.approval_checkpoints) == 1
        assert model.autonomous_remediation_eligibility.default == "human_required"


class TestTaskPacketModel:
    def test_response_roundtrip(self):
        from pearl.models.task_packet import TaskPacket
        data = load_example("task-packets/generate-task-packet.response.json")
        model = TaskPacket.model_validate(data)
        assert model.task_packet_id == "tp_auth_refactor_001"
        assert model.task_type == "refactor"
        assert "auth_flow_change" in model.approval_triggers
        assert model.context_budget.max_tokens_hint == 2400


class TestFindingModel:
    def test_finding_roundtrip(self):
        from pearl.models.finding import Finding
        data = load_example("findings/findings-ingest.request.json")
        finding_data = data["findings"][0]
        model = Finding.model_validate(finding_data)
        assert model.finding_id == "find_cspm_001"
        assert model.source.tool_type == "cspm"
        assert model.severity == "high"


class TestFindingsIngestModel:
    def test_request_roundtrip(self):
        from pearl.models.findings_ingest import FindingsIngestRequest
        data = load_example("findings/findings-ingest.request.json")
        model = FindingsIngestRequest.model_validate(data)
        assert model.source_batch.batch_id == "batch_cspm_20260221_001"
        assert len(model.findings) == 1
        assert model.options.normalize_on_ingest is True

    def test_response_roundtrip(self):
        from pearl.models.findings_ingest import FindingsIngestResponse
        data = load_example("findings/findings-ingest.response.json")
        model = FindingsIngestResponse.model_validate(data)
        assert model.accepted_count == 1
        assert model.quarantined_count == 0


class TestRemediationSpecModel:
    def test_response_roundtrip(self):
        from pearl.models.remediation_spec import RemediationSpec
        data = load_example("remediation/generate-remediation-spec.response.json")
        model = RemediationSpec.model_validate(data)
        assert model.remediation_spec_id == "rs_preprod_egress_fix_001"
        assert model.eligibility == "auto_allowed_with_approval"
        assert model.approval_required is True


class TestApprovalModels:
    def test_request_roundtrip(self):
        from pearl.models.approval import ApprovalRequest
        data = load_example("approvals/create-approval.request.json")
        model = ApprovalRequest.model_validate(data)
        assert model.approval_request_id == "appr_network_change_001"
        assert model.status == "pending"
        assert model.request_type == "network_policy_change"

    def test_decision_request_roundtrip(self):
        from pearl.models.approval import ApprovalDecision
        data = load_example("approvals/decision.request.json")
        model = ApprovalDecision.model_validate(data)
        assert model.decision == "approve"
        assert model.decider_role == "security_review"

    def test_decision_response_roundtrip(self):
        from pearl.models.approval import ApprovalDecision
        data = load_example("approvals/decision.response.json")
        model = ApprovalDecision.model_validate(data)
        assert model.decision == "approve"


class TestExceptionRecordModel:
    def test_request_roundtrip(self):
        from pearl.models.exception import ExceptionRecord
        data = load_example("exceptions/create-exception.request.json")
        model = ExceptionRecord.model_validate(data)
        assert model.exception_id == "exc_preprod_temp_egress_001"
        assert model.status == "active"
        assert model.review_cadence_days == 3


class TestJobStatusModel:
    def test_accepted_response_roundtrip(self):
        from pearl.models.job import JobStatusModel
        data = load_example("compile/compile-context.accepted.response.json")
        model = JobStatusModel.model_validate(data)
        assert model.job_id == "job_compile_001"
        assert model.status == "queued"
        assert model.job_type == "compile_context"


class TestReportModels:
    def test_request_roundtrip(self):
        from pearl.models.report import ReportRequest
        data = load_example("reports/generate-report.request.json")
        model = ReportRequest.model_validate(data)
        assert model.report_type == "release_readiness"
        assert model.format == "json"

    def test_response_roundtrip(self):
        from pearl.models.report import ReportResponse
        data = load_example("reports/generate-report.response.json")
        model = ReportResponse.model_validate(data)
        assert model.report_id == "rpt_release_readiness_001"
        assert model.status == "ready"
        assert model.content["summary"]["ready"] is False
