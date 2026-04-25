"""Tests for report generators and PDF renderer."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_request(detail_level: str = "compliance", fmt: str = "json"):
    req = MagicMock()
    req.detail_level = detail_level
    req.format = fmt
    req.filters = None
    return req


def _make_evaluation(rule_results=None):
    ev = MagicMock()
    ev.evaluation_id = "eval_001"
    ev.source_environment = "dev"
    ev.target_environment = "preprod"
    ev.status = "passed"
    ev.passed_count = 3
    ev.failed_count = 1
    ev.total_count = 4
    ev.progress_pct = 75.0
    ev.blockers = ["some_blocker"]
    ev.rule_results = rule_results or [
        {"rule_type": "unit_tests_exist", "result": "pass", "message": "Unit tests found"},
        {"rule_type": "critical_findings_zero", "result": "fail", "message": "2 critical findings"},
        {"rule_type": "security_review_approval", "result": "pass", "message": "Approved"},
    ]
    return ev


# ---------------------------------------------------------------------------
# Gate Fulfillment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gate_fulfillment_compliance_level():
    """compliance level: structure has gate_summary and gates list."""
    from pearl.services.reports.gate_fulfillment import generate_gate_fulfillment

    mock_db = AsyncMock()
    request = _make_request(detail_level="compliance")

    eval_row = _make_evaluation()

    with (
        patch(
            "pearl.services.reports.gate_fulfillment.PromotionEvaluationRepository"
        ) as MockEvalRepo,
        patch(
            "pearl.services.reports.gate_fulfillment.ApprovalRequestRepository"
        ) as MockApprRepo,
    ):
        eval_instance = AsyncMock()
        eval_instance.get_latest_by_project.return_value = eval_row
        MockEvalRepo.return_value = eval_instance

        appr_instance = AsyncMock()
        appr_instance.list_by_project.return_value = []
        MockApprRepo.return_value = appr_instance

        result = await generate_gate_fulfillment("proj_test", request, mock_db)

    assert "gate_summary" in result
    assert "gates" in result
    assert result["project_id"] == "proj_test"
    assert result["detail_level"] == "compliance"
    assert isinstance(result["gates"], list)
    assert len(result["gates"]) == 3
    assert result["gate_summary"]["total"] == 3

    # compliance level should NOT have "evidence" field on gates
    for g in result["gates"]:
        assert "evidence" not in g


@pytest.mark.asyncio
async def test_gate_fulfillment_full_chain_includes_evidence():
    """full_chain level: evidence field present on each gate."""
    from pearl.services.reports.gate_fulfillment import generate_gate_fulfillment

    mock_db = AsyncMock()
    request = _make_request(detail_level="full_chain")

    eval_row = _make_evaluation()

    # mock evidence package
    ev_pkg = MagicMock()
    ev_pkg.evidence_id = "ev_001"
    ev_pkg.evidence_type = "unit_tests_exist"
    ev_pkg.created_at = None
    ev_pkg.evidence_data = {"artifact_refs": ["s3://bucket/ev_001.json"]}

    with (
        patch(
            "pearl.services.reports.gate_fulfillment.PromotionEvaluationRepository"
        ) as MockEvalRepo,
        patch(
            "pearl.services.reports.gate_fulfillment.EvidencePackageRepository"
        ) as MockEvRepo,
        patch(
            "pearl.services.reports.gate_fulfillment.ApprovalRequestRepository"
        ) as MockApprRepo,
    ):
        eval_instance = AsyncMock()
        eval_instance.get_latest_by_project.return_value = eval_row
        MockEvalRepo.return_value = eval_instance

        ev_instance = AsyncMock()
        ev_instance.list_by_project.return_value = [ev_pkg]
        MockEvRepo.return_value = ev_instance

        appr_instance = AsyncMock()
        appr_instance.list_by_project.return_value = []
        MockApprRepo.return_value = appr_instance

        result = await generate_gate_fulfillment("proj_test", request, mock_db)

    # full_chain level should have "evidence" key on all gates
    for g in result["gates"]:
        assert "evidence" in g
        assert "gate_reasoning" in g

    # The gate matching evidence_type "unit_tests_exist" should have 1 evidence entry
    unit_test_gate = next((g for g in result["gates"] if g["rule"] == "unit_tests_exist"), None)
    assert unit_test_gate is not None
    assert len(unit_test_gate["evidence"]) == 1
    assert unit_test_gate["evidence"][0]["evidence_id"] == "ev_001"


@pytest.mark.asyncio
async def test_gate_fulfillment_no_evaluation_returns_empty():
    """When no evaluation exists, returns an empty gates structure."""
    from pearl.services.reports.gate_fulfillment import generate_gate_fulfillment

    mock_db = AsyncMock()
    request = _make_request(detail_level="compliance")

    with (
        patch(
            "pearl.services.reports.gate_fulfillment.PromotionEvaluationRepository"
        ) as MockEvalRepo,
        patch(
            "pearl.services.reports.gate_fulfillment.ApprovalRequestRepository"
        ) as MockApprRepo,
    ):
        eval_instance = AsyncMock()
        eval_instance.get_latest_by_project.return_value = None
        MockEvalRepo.return_value = eval_instance

        appr_instance = AsyncMock()
        appr_instance.list_by_project.return_value = []
        MockApprRepo.return_value = appr_instance

        result = await generate_gate_fulfillment("proj_test", request, mock_db)

    assert result["gates"] == []
    assert result["gate_summary"]["total"] == 0


# ---------------------------------------------------------------------------
# Elevation Audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_elevation_audit_includes_history():
    """promotions list is populated from PromotionHistoryRepository."""
    from pearl.services.reports.elevation_audit import generate_elevation_audit

    mock_db = AsyncMock()
    request = _make_request(detail_level="compliance")

    from datetime import datetime, timezone

    hist_row = MagicMock()
    hist_row.history_id = "hist_001"
    hist_row.project_id = "proj_test"
    hist_row.source_environment = "dev"
    hist_row.target_environment = "preprod"
    hist_row.evaluation_id = "eval_001"
    hist_row.promoted_by = "usr_admin"
    hist_row.promoted_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    hist_row.details = {"note": "approved"}

    with patch(
        "pearl.services.reports.elevation_audit.PromotionHistoryRepository"
    ) as MockHistRepo:
        hist_instance = AsyncMock()
        hist_instance.list_by_project.return_value = [hist_row]
        MockHistRepo.return_value = hist_instance

        result = await generate_elevation_audit("proj_test", request, mock_db)

    assert result["project_id"] == "proj_test"
    assert len(result["promotions"]) == 1
    p = result["promotions"][0]
    assert p["history_id"] == "hist_001"
    assert p["source_environment"] == "dev"
    assert p["target_environment"] == "preprod"
    assert result["current_environment"] == "preprod"


@pytest.mark.asyncio
async def test_elevation_audit_empty_history():
    """Empty history returns empty promotions list."""
    from pearl.services.reports.elevation_audit import generate_elevation_audit

    mock_db = AsyncMock()
    request = _make_request(detail_level="compliance")

    with patch(
        "pearl.services.reports.elevation_audit.PromotionHistoryRepository"
    ) as MockHistRepo:
        hist_instance = AsyncMock()
        hist_instance.list_by_project.return_value = []
        MockHistRepo.return_value = hist_instance

        result = await generate_elevation_audit("proj_test", request, mock_db)

    assert result["promotions"] == []
    assert result["current_environment"] == "unknown"


# ---------------------------------------------------------------------------
# Findings Remediation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_findings_remediation_compliance_summary():
    """compliance level: summary counts are correct for 3 open findings."""
    from pearl.services.reports.findings_remediation import generate_findings_remediation

    mock_db = AsyncMock()
    request = _make_request(detail_level="compliance")

    from datetime import datetime, timezone

    def _make_finding(fid, severity, status, source_tool="manual"):
        f = MagicMock()
        f.finding_id = fid
        f.title = f"Finding {fid}"
        f.severity = severity
        f.status = status
        f.source = {"tool": source_tool}
        f.detected_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
        f.resolved_at = None
        return f

    findings = [
        _make_finding("find_001", "critical", "open", "sonarqube"),
        _make_finding("find_002", "high", "open", "mass"),
        _make_finding("find_003", "low", "resolved", "manual"),
    ]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = findings
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await generate_findings_remediation("proj_test", request, mock_db)

    assert result["project_id"] == "proj_test"
    assert result["detail_level"] == "compliance"
    assert result["summary"]["total"] == 3
    assert result["summary"]["by_severity"]["critical"] == 1
    assert result["summary"]["by_severity"]["high"] == 1
    assert result["summary"]["by_severity"]["low"] == 1
    assert result["summary"]["by_status"]["open"] == 2
    assert result["summary"]["by_status"]["resolved"] == 1
    assert result["summary"]["resolved_pct"] == pytest.approx(33.3, abs=0.1)
    assert result["summary"]["by_source"]["sonarqube"] == 1
    assert result["summary"]["by_source"]["mass"] == 1
    # full_chain findings list should NOT be present at compliance level
    assert "findings" not in result


@pytest.mark.asyncio
async def test_findings_remediation_full_chain_per_finding():
    """full_chain level: findings list present with required fields."""
    from pearl.services.reports.findings_remediation import generate_findings_remediation

    mock_db = AsyncMock()
    request = _make_request(detail_level="full_chain")

    from datetime import datetime, timezone

    f = MagicMock()
    f.finding_id = "find_001"
    f.title = "SQL Injection"
    f.severity = "critical"
    f.status = "open"
    f.source = {"tool": "sonarqube", "artifact_refs": ["s3://bucket/scan.json"]}
    f.detected_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    f.resolved_at = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [f]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await generate_findings_remediation("proj_test", request, mock_db)

    assert "findings" in result
    assert len(result["findings"]) == 1
    fi = result["findings"][0]
    assert fi["finding_id"] == "find_001"
    assert fi["severity"] == "critical"
    assert fi["source_tool"] == "sonarqube"
    assert fi["status"] == "open"
    assert "detected_at" in fi
    assert "artifact_refs" in fi


# ---------------------------------------------------------------------------
# PDF Renderer
# ---------------------------------------------------------------------------


def test_pdf_renderer_produces_bytes():
    """render_report_pdf returns non-empty bytes when weasyprint is available."""
    weasyprint = pytest.importorskip("weasyprint")  # skip if not installed

    from pearl.services.reports.pdf_renderer import render_report_pdf

    report_data = {
        "project_id": "proj_test",
        "report_type": "gate_fulfillment",
        "content": {
            "gate_summary": {"passed": 2, "failed": 1, "total": 3, "pct": 66.7},
            "gates": [
                {"rule": "unit_tests_exist", "status": "pass", "message": "OK", "evidence_count": 0},
                {"rule": "critical_findings_zero", "status": "fail", "message": "1 critical", "evidence_count": 0},
            ],
            "blockers": ["critical_findings_zero: 1 critical"],
            "detail_level": "compliance",
            "environment_target": "preprod",
        },
        "generated_at": "2025-01-01T00:00:00+00:00",
        "detail_level": "compliance",
    }

    pdf_bytes = render_report_pdf(report_data)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 100  # actual PDF has content


def test_pdf_renderer_missing_weasyprint_raises():
    """render_report_pdf raises ImportError when weasyprint is not available."""
    with patch.dict("sys.modules", {"weasyprint": None}):
        from pearl.services.reports import pdf_renderer

        # Patch _get_weasyprint to simulate missing module
        original = pdf_renderer._get_weasyprint

        def raise_import():
            raise ImportError("weasyprint not installed")

        pdf_renderer._get_weasyprint = raise_import
        try:
            with pytest.raises(ImportError):
                pdf_renderer.render_report_pdf({"project_id": "p", "report_type": "x", "content": {}, "generated_at": "now", "detail_level": "compliance"})
        finally:
            pdf_renderer._get_weasyprint = original


# ---------------------------------------------------------------------------
# ReportRequest model — detail_level field
# ---------------------------------------------------------------------------


def test_report_request_default_detail_level():
    """ReportRequest defaults detail_level to 'compliance'."""
    from pearl.models.report import ReportRequest

    r = ReportRequest(
        schema_version="1.1",
        report_type="gate_fulfillment",
        format="json",
    )
    assert r.detail_level == "compliance"


def test_report_request_full_chain_detail_level():
    """ReportRequest accepts 'full_chain' detail_level."""
    from pearl.models.report import ReportRequest

    r = ReportRequest(
        schema_version="1.1",
        report_type="findings_remediation",
        format="json",
        detail_level="full_chain",
    )
    assert r.detail_level == "full_chain"


def test_new_report_types_in_enum():
    """New ReportType values are valid enum members."""
    from pearl.models.enums import ReportType

    assert ReportType.GATE_FULFILLMENT == "gate_fulfillment"
    assert ReportType.ELEVATION_AUDIT == "elevation_audit"
    assert ReportType.FINDINGS_REMEDIATION == "findings_remediation"


# ---------------------------------------------------------------------------
# Enrichment error accumulation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_release_readiness_enrichment_failure_populates_errors(client):
    """When a report enrichment block fails, response must include enrichment_errors list."""
    from unittest.mock import patch, AsyncMock

    # Create a project with all required fields
    resp = await client.post(
        "/api/v1/projects",
        json={
            "schema_version": "1.1",
            "project_id": "proj_enrich_err_test",
            "name": "Enrichment Error Test",
            "owner_team": "platform",
            "business_criticality": "low",
            "external_exposure": "internal_only",
            "ai_enabled": False,
        },
    )
    assert resp.status_code == 201
    project_id = resp.json()["project_id"]

    # Patch FindingRepository to raise so the findings enrichment block fails
    with patch(
        "pearl.repositories.finding_repo.FindingRepository.list_by_field",
        AsyncMock(side_effect=RuntimeError("injected findings failure")),
    ):
        resp = await client.post(
            f"/api/v1/projects/{project_id}/reports/generate",
            json={"schema_version": "1.1", "report_type": "release_readiness", "format": "json"},
        )

    assert resp.status_code == 200
    body = resp.json()
    content = body.get("content", body)
    assert "enrichment_errors" in content, "enrichment_errors key must be present when a section fails"
    assert len(content["enrichment_errors"]) >= 1
    assert any("findings" in e for e in content["enrichment_errors"])
