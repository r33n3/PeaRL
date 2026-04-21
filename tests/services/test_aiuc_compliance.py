# tests/services/test_aiuc_compliance.py
import pytest
from pearl.services.promotion.aiuc_mapping import (
    aiuc_controls_satisfied_by_framework,
    aiuc_controls_blocked_by_findings,
    AIUC1_MANDATORY_PILOT,
    compute_aiuc_compliance,
)


def test_framework_owasp_llm01_satisfies_b005():
    satisfied = aiuc_controls_satisfied_by_framework("owasp_llm", "llm01_prompt_injection")
    assert "B005.1" in satisfied
    assert "B005.2" in satisfied


def test_framework_nist_rmf_oversight_satisfies_c005():
    satisfied = aiuc_controls_satisfied_by_framework("nist_rmf", "oversight_mechanism")
    assert "C005.1" in satisfied
    assert "C005.2" in satisfied


def test_unknown_framework_returns_empty():
    satisfied = aiuc_controls_satisfied_by_framework("nonexistent", "ctrl")
    assert satisfied == []


def test_finding_prompt_injection_blocks_b005():
    blocked = aiuc_controls_blocked_by_findings(["prompt_injection"])
    assert "B005.1" in blocked


def test_finding_pii_exposure_blocks_a006():
    blocked = aiuc_controls_blocked_by_findings(["pii_exposure"])
    assert "A006.1" in blocked


def test_mandatory_pilot_controls_not_empty():
    assert len(AIUC1_MANDATORY_PILOT) >= 15


class _FakeEvidence:
    def __init__(self, evidence_type, control_id=None, framework=None):
        self.evidence_type = evidence_type
        self.evidence_data = {}
        if control_id:
            self.evidence_data["control_id"] = control_id
        if framework:
            self.evidence_data["framework"] = framework


class _FakeFinding:
    def __init__(self, category, status="open"):
        self.category = category
        self.status = status


class _FakeCtx:
    def __init__(self, evidence=None, findings=None):
        self.evidence_packages = evidence or []
        self.open_findings = findings or []


def test_compute_aiuc_compliance_full_pass():
    # LLM01 attestation satisfies B005.1, B005.2
    ev = [_FakeEvidence("attestation", control_id="owasp_llm/llm01_prompt_injection")]
    ctx = _FakeCtx(evidence=ev)
    result = compute_aiuc_compliance(ctx, AIUC1_MANDATORY_PILOT)
    assert "B005.1" in result["satisfied"]
    assert "B005.2" in result["satisfied"]


def test_compute_aiuc_compliance_finding_blocks_satisfied():
    ev = [_FakeEvidence("attestation", control_id="owasp_llm/llm01_prompt_injection")]
    findings = [_FakeFinding("prompt_injection")]
    ctx = _FakeCtx(evidence=ev, findings=findings)
    result = compute_aiuc_compliance(ctx, AIUC1_MANDATORY_PILOT)
    # B005.1 satisfied by evidence BUT blocked by open finding
    assert "B005.1" in result["blocked"]
    assert "B005.1" not in result["net_satisfied"]


def test_compute_aiuc_compliance_outstanding_list():
    ctx = _FakeCtx()
    result = compute_aiuc_compliance(ctx, ["B005.1", "C005.1"])
    assert "B005.1" in result["outstanding"]
    assert "C005.1" in result["outstanding"]
    assert result["score_pct"] == 0.0


def test_compute_aiuc_compliance_score_100():
    # Directly attest both mandatory controls
    ev = [
        _FakeEvidence("attestation", control_id="aiuc1/B005.1"),
        _FakeEvidence("attestation", control_id="aiuc1/C005.1"),
    ]
    ctx = _FakeCtx(evidence=ev)
    result = compute_aiuc_compliance(ctx, ["B005.1", "C005.1"])
    assert result["score_pct"] == 100.0
    assert result["outstanding"] == []
