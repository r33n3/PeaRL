"""Tests for promotion gate Pydantic models and enum validation."""

import pytest
from datetime import datetime, timezone

from pearl.models.enums import (
    Environment,
    GateEvaluationStatus,
    GateRuleResult,
    GateRuleType,
    PromotionRequestStatus,
)
from pearl.models.promotion import (
    GateRuleDefinition,
    PromotionEvaluation,
    PromotionGate,
    PromotionHistory,
    PromotionReadiness,
    PromotionRequest,
    RuleEvaluationResult,
)


class TestGateRuleDefinition:
    def test_valid_rule(self):
        rule = GateRuleDefinition(
            rule_id="rule_project_registered",
            rule_type=GateRuleType.PROJECT_REGISTERED,
            description="Project must be registered",
            required=True,
            ai_only=False,
        )
        assert rule.rule_id == "rule_project_registered"
        assert rule.rule_type == GateRuleType.PROJECT_REGISTERED
        assert rule.required is True
        assert rule.ai_only is False

    def test_rule_with_threshold(self):
        rule = GateRuleDefinition(
            rule_id="rule_unit_test_coverage",
            rule_type=GateRuleType.UNIT_TEST_COVERAGE,
            description="Coverage >= 80%",
            threshold=80.0,
        )
        assert rule.threshold == 80.0

    def test_rule_with_parameters(self):
        rule = GateRuleDefinition(
            rule_id="rule_custom",
            rule_type=GateRuleType.MASS_RISK_ACCEPTABLE,
            description="MASS risk",
            parameters={"max_cvss": 7.0},
        )
        assert rule.parameters == {"max_cvss": 7.0}

    def test_invalid_rule_id_pattern(self):
        with pytest.raises(Exception):
            GateRuleDefinition(
                rule_id="bad_id",
                rule_type=GateRuleType.PROJECT_REGISTERED,
                description="Bad ID",
            )


class TestPromotionGate:
    def test_valid_gate(self):
        gate = PromotionGate(
            gate_id="gate_sandbox_to_dev",
            source_environment=Environment.SANDBOX,
            target_environment=Environment.DEV,
            rules=[
                GateRuleDefinition(
                    rule_id="rule_project_registered",
                    rule_type=GateRuleType.PROJECT_REGISTERED,
                    description="Project must be registered",
                )
            ],
        )
        assert gate.gate_id == "gate_sandbox_to_dev"
        assert gate.source_environment == Environment.SANDBOX
        assert gate.target_environment == Environment.DEV
        assert len(gate.rules) == 1

    def test_gate_requires_at_least_one_rule(self):
        with pytest.raises(Exception):
            PromotionGate(
                gate_id="gate_empty",
                source_environment=Environment.SANDBOX,
                target_environment=Environment.DEV,
                rules=[],
            )


class TestRuleEvaluationResult:
    def test_pass_result(self):
        result = RuleEvaluationResult(
            rule_id="rule_project_registered",
            rule_type=GateRuleType.PROJECT_REGISTERED,
            result=GateRuleResult.PASS,
            message="Project is registered",
        )
        assert result.result == GateRuleResult.PASS
        assert result.exception_id is None

    def test_fail_with_exception(self):
        result = RuleEvaluationResult(
            rule_id="rule_critical_findings_zero",
            rule_type=GateRuleType.CRITICAL_FINDINGS_ZERO,
            result=GateRuleResult.FAIL,
            message="1 critical finding open",
            exception_id="exc_001",
        )
        assert result.result == GateRuleResult.FAIL
        assert result.exception_id == "exc_001"


class TestPromotionEvaluation:
    def test_valid_evaluation(self):
        now = datetime.now(timezone.utc)
        ev = PromotionEvaluation(
            evaluation_id="eval_test001",
            project_id="proj_test",
            gate_id="gate_sandbox_to_dev",
            source_environment=Environment.SANDBOX,
            target_environment=Environment.DEV,
            status=GateEvaluationStatus.PASSED,
            rule_results=[
                RuleEvaluationResult(
                    rule_id="rule_project_registered",
                    rule_type=GateRuleType.PROJECT_REGISTERED,
                    result=GateRuleResult.PASS,
                    message="OK",
                )
            ],
            passed_count=1,
            failed_count=0,
            total_count=1,
            progress_pct=100.0,
            evaluated_at=now,
        )
        assert ev.status == GateEvaluationStatus.PASSED
        assert ev.progress_pct == 100.0

    def test_partial_evaluation(self):
        ev = PromotionEvaluation(
            evaluation_id="eval_partial001",
            project_id="proj_test",
            gate_id="gate_dev_to_pilot",
            source_environment=Environment.DEV,
            target_environment=Environment.PILOT,
            status=GateEvaluationStatus.PARTIAL,
            rule_results=[],
            passed_count=5,
            failed_count=3,
            total_count=8,
            progress_pct=62.5,
            blockers=["Missing security review", "Critical findings"],
        )
        assert ev.status == GateEvaluationStatus.PARTIAL
        assert len(ev.blockers) == 2


class TestPromotionRequest:
    def test_valid_request(self):
        req = PromotionRequest(
            request_id="promreq_001",
            project_id="proj_test",
            evaluation_id="eval_001",
            source_environment=Environment.DEV,
            target_environment=Environment.PILOT,
            status=PromotionRequestStatus.PENDING_APPROVAL,
        )
        assert req.status == PromotionRequestStatus.PENDING_APPROVAL


class TestPromotionHistory:
    def test_valid_history(self):
        hist = PromotionHistory(
            history_id="promhist_001",
            project_id="proj_test",
            source_environment=Environment.DEV,
            target_environment=Environment.PILOT,
            evaluation_id="eval_001",
            promoted_by="admin@example.com",
            promoted_at=datetime.now(timezone.utc),
        )
        assert hist.promoted_by == "admin@example.com"


class TestPromotionReadiness:
    def test_valid_readiness(self):
        r = PromotionReadiness(
            current_environment=Environment.DEV,
            next_environment=Environment.PILOT,
            status=GateEvaluationStatus.PARTIAL,
            progress_pct=75.0,
            passed_count=9,
            total_count=12,
            blockers=["Missing IAM roles"],
        )
        assert r.progress_pct == 75.0
        assert r.blockers == ["Missing IAM roles"]


class TestGateRuleTypeEnum:
    def test_all_rule_types_exist(self):
        expected_types = [
            "project_registered", "org_baseline_attached", "app_spec_defined",
            "no_hardcoded_secrets", "unit_tests_exist", "unit_test_coverage",
            "critical_findings_zero", "high_findings_zero", "security_baseline_tests",
            "mass_scan_completed", "no_prompt_injection", "guardrails_verified",
            "fairness_case_defined", "fairness_requirements_met",
        ]
        for t in expected_types:
            assert GateRuleType(t) is not None

    def test_environment_order(self):
        envs = [Environment.SANDBOX, Environment.DEV, Environment.PILOT, Environment.PREPROD, Environment.PROD]
        values = [e.value for e in envs]
        assert values == ["sandbox", "dev", "pilot", "preprod", "prod"]


class TestGateEvaluationStatus:
    def test_status_values(self):
        assert GateEvaluationStatus.PASSED.value == "passed"
        assert GateEvaluationStatus.FAILED.value == "failed"
        assert GateEvaluationStatus.PARTIAL.value == "partial"
