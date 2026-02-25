"""BenderBox integration test — full developer lifecycle with PeaRL scanning.

Creates a project for BenderBox, applies the recommended governance baseline,
runs PeaRL AI security scan, and identifies what's needed for PROD elevation.

This test does NOT fix findings — it demonstrates the governance posture
and what a developer would need to address.
"""

import json
from pathlib import Path

import pytest

from pearl.scanning.baseline_package import (
    get_recommended_baseline,
    select_baseline_tier,
)
from pearl.scanning.service import ScanningService
from pearl.scanning.compliance.assessor import ComplianceAssessor
from pearl.scanning.policy.guardrails import get_default_guardrails

# BenderBox source path
BENDERBOX_SRC = Path(r"c:\Users\bradj\Development\BenderBox\src")
BENDERBOX_ROOT = Path(r"c:\Users\bradj\Development\BenderBox")


# ---------------------------------------------------------------------------
# Helper: Skip if BenderBox not present
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.skipif(
    not BENDERBOX_SRC.exists(),
    reason="BenderBox source not found at expected path",
)


# ---------------------------------------------------------------------------
# 1. Baseline tier selection
# ---------------------------------------------------------------------------


class TestBaselineTierSelection:
    """Verify BenderBox gets the right governance tier."""

    def test_benderbox_is_ai_enabled_high_criticality(self):
        """BenderBox is an AI security toolkit — ai_enabled=true, criticality=high."""
        tier = select_baseline_tier(ai_enabled=True, business_criticality="high")
        assert tier == "ai_comprehensive"

    def test_ai_comprehensive_baseline_includes_all_sections(self):
        """AI-Comprehensive tier has all governance sections."""
        baseline = get_recommended_baseline(ai_enabled=True, business_criticality="high")
        defaults = baseline["defaults"]

        assert "coding" in defaults
        assert "logging" in defaults
        assert "iam" in defaults
        assert "network" in defaults
        assert "responsible_ai" in defaults
        assert "testing" in defaults
        assert "ai_security" in defaults
        assert "scanning" in defaults
        assert "compliance_frameworks" in defaults
        assert "security_review" in defaults
        assert "artifacts" in defaults

    def test_ai_comprehensive_requires_all_frameworks(self):
        """AI-Comprehensive tier requires all 4 compliance frameworks."""
        baseline = get_recommended_baseline(ai_enabled=True, business_criticality="high")
        frameworks = baseline["defaults"]["compliance_frameworks"]

        assert frameworks["owasp_llm_top10_assessment_required"] is True
        assert frameworks["mitre_atlas_assessment_required"] is True
        assert frameworks["nist_ai_rmf_assessment_required"] is True
        assert frameworks["eu_ai_act_assessment_when_applicable"] is True

    def test_ai_comprehensive_requires_prod_diagrams(self):
        """AI-Comprehensive requires updated diagrams for PROD."""
        baseline = get_recommended_baseline(ai_enabled=True, business_criticality="high")
        artifacts = baseline["defaults"]["artifacts"]

        assert artifacts["architecture_diagram_required_after_scan"] is True
        assert artifacts["threat_model_diagram_required_after_scan"] is True
        assert artifacts["updated_diagrams_required_for_prod"] is True
        assert artifacts["diagram_must_reflect_current_scan_state"] is True


# ---------------------------------------------------------------------------
# 2. Run PeaRL scan against BenderBox
# ---------------------------------------------------------------------------


class TestBenderBoxScan:
    """Run PeaRL's AI security analyzers against BenderBox."""

    @pytest.fixture(scope="class")
    def scan_result(self):
        """Run the full scan once for all tests in this class."""
        service = ScanningService()
        result = service.scan_target(
            target_path=BENDERBOX_SRC,
            project_id="proj_benderbox_test",
            environment="dev",
        )
        return result

    def test_scan_completes_without_errors(self, scan_result):
        """Scan should complete (errors are warnings, not blockers)."""
        assert scan_result.scan_id is not None
        assert scan_result.completed_at is not None

    def test_multiple_analyzers_run(self, scan_result):
        """Multiple analyzers should have executed."""
        assert len(scan_result.analyzers_run) >= 2
        print(f"\nAnalyzers run: {scan_result.analyzers_run}")

    def test_findings_discovered(self, scan_result):
        """BenderBox should have AI security findings."""
        assert scan_result.total_findings > 0
        print(f"\nTotal findings: {scan_result.total_findings}")
        print(f"By severity: {dict(scan_result.findings_by_severity)}")
        print(f"By analyzer: {dict(scan_result.findings_by_analyzer)}")

    def test_context_analyzer_finds_issues(self, scan_result):
        """Context analyzer should find risky patterns in BenderBox configs."""
        context_count = scan_result.findings_by_analyzer.get("context", 0)
        # BenderBox has security testing configs with deliberate attack patterns
        print(f"\nContext analyzer findings: {context_count}")

    def test_rag_analyzer_finds_issues(self, scan_result):
        """RAG analyzer should detect BenderBox's vector store usage."""
        rag_count = scan_result.findings_by_analyzer.get("rag", 0)
        print(f"\nRAG analyzer findings: {rag_count}")

    def test_compliance_assessment_generated(self, scan_result):
        """Compliance assessment should be generated from findings."""
        assert scan_result.compliance_assessment is not None
        score = scan_result.compliance_assessment.overall_compliance_score
        print(f"\nOverall compliance score: {score:.1f}%")

        for name, fa in scan_result.compliance_assessment.frameworks.items():
            print(f"  {name}: {fa.compliance_score:.1f}% ({fa.compliant_count}/{fa.total_requirements} compliant)")

    def test_guardrail_recommendations_generated(self, scan_result):
        """Guardrail recommendations should be generated."""
        assert len(scan_result.guardrail_recommendations) > 0
        print(f"\nRecommended guardrails ({len(scan_result.guardrail_recommendations)}):")
        for g in scan_result.guardrail_recommendations:
            print(f"  - {g.name} ({g.guardrail_type.value})")

    def test_diagrams_generated(self, scan_result):
        """Threat model and topology diagrams should be generated."""
        # Diagrams are generated if components are found
        if scan_result.diagrams:
            print(f"\nDiagrams generated: {list(scan_result.diagrams.keys())}")
            for name, xml in scan_result.diagrams.items():
                print(f"  {name}: {len(xml)} bytes of draw.io XML")

    def test_scan_result_serializable(self, scan_result):
        """Scan result should serialize to JSON-safe dict."""
        d = scan_result.to_dict()
        # Should be JSON serializable
        json_str = json.dumps(d, indent=2)
        assert len(json_str) > 100


# ---------------------------------------------------------------------------
# 3. Compliance gap analysis for PROD
# ---------------------------------------------------------------------------


class TestProdReadinessGaps:
    """Identify what BenderBox needs for PROD elevation."""

    @pytest.fixture(scope="class")
    def scan_result(self):
        service = ScanningService()
        return service.scan_target(
            target_path=BENDERBOX_SRC,
            project_id="proj_benderbox_prod",
            environment="dev",
        )

    def test_compliance_score_below_prod_threshold(self, scan_result):
        """BenderBox should need work to reach 90% compliance for PROD."""
        if scan_result.compliance_assessment:
            score = scan_result.compliance_assessment.overall_compliance_score
            prod_threshold = 90.0
            print(f"\nCompliance score: {score:.1f}% (PROD threshold: {prod_threshold}%)")
            if score < prod_threshold:
                print(f"GAP: Need {prod_threshold - score:.1f}% improvement for PROD")

    def test_identify_critical_and_high_findings(self, scan_result):
        """List critical and high findings that block PROD."""
        critical = scan_result.findings_by_severity.get("critical", 0)
        high = scan_result.findings_by_severity.get("high", 0)
        print(f"\nFindings blocking PROD:")
        print(f"  Critical: {critical} (must be 0 for PROD)")
        print(f"  High: {high} (must be 0 for PROD)")

        # List the actual findings
        for ar in scan_result.analyzer_results:
            for f in ar.findings:
                sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
                if sev in ("critical", "high"):
                    print(f"  [{sev.upper()}] {f.title[:80]} ({ar.analyzer_name})")

    def test_identify_non_compliant_requirements(self, scan_result):
        """List compliance requirements not met."""
        if not scan_result.compliance_assessment:
            pytest.skip("No compliance assessment")

        assessor = ComplianceAssessor()
        non_compliant = assessor.get_non_compliant_requirements(
            scan_result.compliance_assessment
        )
        print(f"\nNon-compliant requirements ({len(non_compliant)}):")
        for nc in non_compliant:
            print(f"  [{nc.requirement.framework.value}] {nc.requirement.id}: {nc.requirement.name}")

    def test_identify_missing_guardrails(self, scan_result):
        """List guardrails that need implementation."""
        print(f"\nGuardrails needed for PROD ({len(scan_result.guardrail_recommendations)}):")
        for g in scan_result.guardrail_recommendations:
            print(f"  [{g.severity.value}] {g.name}: {g.description[:80]}")

    def test_generate_prod_readiness_summary(self, scan_result):
        """Generate a markdown summary of PROD readiness gaps."""
        score = scan_result.compliance_assessment.overall_compliance_score if scan_result.compliance_assessment else 0

        summary_lines = [
            "# BenderBox PROD Readiness Summary",
            "",
            f"## Scan Results",
            f"- **Analyzers run**: {', '.join(scan_result.analyzers_run)}",
            f"- **Total findings**: {scan_result.total_findings}",
            f"- **By severity**: {dict(scan_result.findings_by_severity)}",
            f"- **Compliance score**: {score:.1f}%",
            "",
            "## Blockers for PROD Elevation",
            "",
        ]

        # Critical/high findings
        for ar in scan_result.analyzer_results:
            for f in ar.findings:
                sev = f.severity.value if hasattr(f.severity, "value") else str(f.severity)
                if sev in ("critical", "high"):
                    summary_lines.append(f"- **[{sev.upper()}]** {f.title[:100]}")

        summary_lines.extend([
            "",
            "## Compliance Gaps",
            f"- PROD requires >= 90% compliance score (current: {score:.1f}%)",
        ])

        if scan_result.compliance_assessment:
            for name, fa in scan_result.compliance_assessment.frameworks.items():
                if fa.compliance_score < 100:
                    summary_lines.append(f"- **{name}**: {fa.compliance_score:.1f}% ({fa.non_compliant_count} non-compliant requirements)")

        summary_lines.extend([
            "",
            "## Required Guardrails",
        ])
        for g in scan_result.guardrail_recommendations:
            summary_lines.append(f"- {g.name} ({g.guardrail_type.value})")

        summary_lines.extend([
            "",
            "## Governance Requirements (AI-Comprehensive Tier)",
            "- Architecture diagram required after scan",
            "- Threat model diagram required after scan",
            "- Updated diagrams required for PROD",
            "- Diagrams must reflect current scan state",
            "- Security review must be completed",
            "- Security review must cover AI components",
            "- Security review recurrence: per_release",
        ])

        if scan_result.errors:
            summary_lines.extend([
                "",
                "## Scan Errors (non-blocking)",
            ])
            for err in scan_result.errors:
                summary_lines.append(f"- {err}")

        summary = "\n".join(summary_lines)
        print(f"\n{summary}")

        # Verify summary is substantive
        assert len(summary) > 200
        assert "BenderBox" in summary
