"""Tests for fairness governance Pydantic models."""

import pytest
from datetime import datetime, timezone

from pearl.models.enums import (
    AttestationStatus,
    Environment,
    EvidenceType,
    ExceptionStatus,
    FairnessCriticality,
    GateMode,
    RiskTier,
)
from pearl.models.fairness import (
    Attestation,
    ContextContract,
    ContextPack,
    ContextReceipt,
    EvidencePackage,
    FairnessCase,
    FairnessException,
    FairnessRequirement,
    FairnessRequirementsSpec,
    MonitoringSignal,
)


class TestFairnessCase:
    def test_valid_case(self):
        fc = FairnessCase(
            fc_id="fc_test001",
            project_id="proj_test",
            risk_tier=RiskTier.R2,
            fairness_criticality=FairnessCriticality.HIGH,
            system_description="AI customer support chatbot",
            stakeholders=["customers", "support_agents"],
            fairness_principles=["equal_treatment", "transparency"],
        )
        assert fc.risk_tier == RiskTier.R2
        assert fc.fairness_criticality == FairnessCriticality.HIGH
        assert len(fc.stakeholders) == 2

    def test_invalid_fc_id(self):
        with pytest.raises(Exception):
            FairnessCase(
                fc_id="bad_id",
                project_id="proj_test",
                risk_tier=RiskTier.R0,
                fairness_criticality=FairnessCriticality.LOW,
            )


class TestFairnessRequirement:
    def test_prohibit_requirement(self):
        fr = FairnessRequirement(
            requirement_id="fr_001",
            statement="No demographic discrimination in recommendations",
            requirement_type="prohibit",
            gate_mode_per_env={"dev": GateMode.WARN, "prod": GateMode.BLOCK},
        )
        assert fr.requirement_type == "prohibit"
        assert fr.gate_mode_per_env["prod"] == GateMode.BLOCK

    def test_threshold_requirement(self):
        fr = FairnessRequirement(
            requirement_id="fr_002",
            statement="Equal opportunity score must be >= 0.8",
            requirement_type="threshold",
            threshold_value=0.8,
            threshold_metric="equal_opportunity_score",
        )
        assert fr.threshold_value == 0.8

    def test_invalid_requirement_type(self):
        with pytest.raises(Exception):
            FairnessRequirement(
                requirement_id="fr_003",
                statement="Invalid",
                requirement_type="invalid_type",
            )


class TestFairnessRequirementsSpec:
    def test_valid_frs(self):
        frs = FairnessRequirementsSpec(
            frs_id="frs_001",
            project_id="proj_test",
            requirements=[
                FairnessRequirement(
                    requirement_id="fr_001",
                    statement="Test requirement",
                    requirement_type="require",
                )
            ],
            version="1.0",
        )
        assert frs.frs_id == "frs_001"
        assert len(frs.requirements) == 1

    def test_frs_requires_at_least_one_requirement(self):
        with pytest.raises(Exception):
            FairnessRequirementsSpec(
                frs_id="frs_002",
                project_id="proj_test",
                requirements=[],
            )


class TestAttestation:
    def test_unsigned(self):
        att = Attestation(
            attestation_id="att_001",
            signed_by="reviewer@example.com",
            status=AttestationStatus.UNSIGNED,
        )
        assert att.status == AttestationStatus.UNSIGNED

    def test_signed(self):
        att = Attestation(
            attestation_id="att_002",
            signed_by="reviewer@example.com",
            signed_at=datetime.now(timezone.utc),
            status=AttestationStatus.SIGNED,
            signature_ref="sig://sha256:abc123",
        )
        assert att.status == AttestationStatus.SIGNED


class TestEvidencePackage:
    def test_valid_evidence(self):
        ev = EvidencePackage(
            evidence_id="fe_001",
            project_id="proj_test",
            environment=Environment.DEV,
            evidence_type=EvidenceType.BIAS_BENCHMARK,
            summary="Bias benchmark results",
            attestation_status=AttestationStatus.UNSIGNED,
            freshness_days=30,
        )
        assert ev.evidence_type == EvidenceType.BIAS_BENCHMARK
        assert ev.freshness_days == 30


class TestFairnessException:
    def test_valid_exception(self):
        fe = FairnessException(
            exception_id="fer_001",
            project_id="proj_test",
            requirement_id="fr_001",
            rationale="Cannot meet threshold due to data scarcity",
            compensating_controls=["manual_review", "sampling_audit"],
            status=ExceptionStatus.ACTIVE,
            approved_by="governance@example.com",
        )
        assert fe.status == ExceptionStatus.ACTIVE
        assert len(fe.compensating_controls) == 2


class TestMonitoringSignal:
    def test_valid_signal(self):
        sig = MonitoringSignal(
            signal_id="sig_001",
            project_id="proj_test",
            environment=Environment.PROD,
            signal_type="fairness_drift",
            value=0.05,
            threshold=0.1,
        )
        assert sig.value < sig.threshold


class TestContextContract:
    def test_valid_contract(self):
        cc = ContextContract(
            cc_id="cc_001",
            required_artifacts=["fairness_case", "evidence_package", "attestation"],
            gate_mode_per_env={"dev": GateMode.WARN, "prod": GateMode.BLOCK},
        )
        assert len(cc.required_artifacts) == 3


class TestContextPack:
    def test_valid_pack(self):
        cp = ContextPack(
            cp_id="cp_001",
            project_id="proj_test",
            environment=Environment.DEV,
            pack_data={"fairness_case": {}, "evidence": {}},
            artifact_hashes={"fairness_case": "sha256:abc"},
        )
        assert "fairness_case" in cp.pack_data


class TestContextReceipt:
    def test_valid_receipt(self):
        cr = ContextReceipt(
            cr_id="cr_001",
            project_id="proj_test",
            commit_hash="abc123def456",
            agent_id="claude-code",
            tool_calls=["read_fairness_case", "read_evidence"],
            artifact_hashes={"fairness_case": "sha256:abc"},
        )
        assert cr.agent_id == "claude-code"
        assert len(cr.tool_calls) == 2
