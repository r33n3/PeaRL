"""Unit tests for the SonarQube adapter."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pearl.integrations.adapters.sonarqube import SonarQubeAdapter
from pearl.integrations.config import AuthConfig, IntegrationEndpoint
from pearl.models.enums import IntegrationCategory, IntegrationType


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_endpoint(labels: dict | None = None) -> IntegrationEndpoint:
    return IntegrationEndpoint(
        endpoint_id="ep_sonar_test",
        name="SonarQube Test",
        adapter_type="sonarqube",
        integration_type=IntegrationType.SOURCE,
        category=IntegrationCategory.SAST,
        base_url="http://sonarqube:9090",
        auth=AuthConfig(auth_type="bearer", bearer_token_env="SONAR_TOKEN"),
        labels=labels or {"project_key": "my-project"},
    )


def _raw_vulnerability_issue() -> dict:
    return {
        "key": "AXoW-abcd1234",
        "rule": "java:S2629",
        "severity": "CRITICAL",
        "component": "my-project:src/main/Auth.java",
        "project": "my-project",
        "type": "VULNERABILITY",
        "message": "Remove this invocation of 'log' or add a guard check.",
        "creationDate": "2026-01-15T10:00:00+0000",
        "securityStandards": ["cwe:117", "cwe:532"],
    }


def _raw_code_smell_issue() -> dict:
    return {
        "key": "AXoW-code001",
        "rule": "java:S1481",
        "severity": "MINOR",
        "component": "my-project:src/main/Service.java",
        "project": "my-project",
        "type": "CODE_SMELL",
        "message": "Remove this unused 'x' local variable.",
        "creationDate": "2026-01-16T08:00:00+0000",
        "securityStandards": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNormalizeIssue:
    def test_normalize_issue_vulnerability(self):
        """Vulnerability type should map to high severity and sast source_type."""
        raw = _raw_vulnerability_issue()
        adapter = SonarQubeAdapter()

        finding = adapter._normalize_issue(raw)

        assert finding.external_id == "AXoW-abcd1234"
        assert finding.source_tool == "sonarqube"
        assert finding.source_type == "sast"
        assert finding.severity == "high"  # CRITICAL → high
        assert finding.title == "Remove this invocation of 'log' or add a guard check."
        assert finding.cwe_ids == ["CWE-117", "CWE-532"]
        assert finding.category == "security"

    def test_normalize_issue_code_smell(self):
        """CODE_SMELL type should map to low severity and sast source_type."""
        raw = _raw_code_smell_issue()
        adapter = SonarQubeAdapter()

        finding = adapter._normalize_issue(raw)

        assert finding.external_id == "AXoW-code001"
        assert finding.source_tool == "sonarqube"
        assert finding.source_type == "sast"
        assert finding.severity == "low"  # MINOR → low
        assert finding.cwe_ids is None  # no securityStandards CWE
        assert finding.category == "security"

    def test_normalize_issue_blocker_maps_to_critical(self):
        raw = {
            "key": "blocker-001",
            "severity": "BLOCKER",
            "type": "BUG",
            "message": "NullPointerException",
            "component": "my-project:src/Foo.java",
            "securityStandards": [],
        }
        finding = SonarQubeAdapter._normalize_issue(raw)
        assert finding.severity == "critical"

    def test_normalize_issue_detected_at_parsed(self):
        raw = _raw_vulnerability_issue()
        finding = SonarQubeAdapter._normalize_issue(raw)
        assert finding.detected_at.year == 2026
        assert finding.detected_at.month == 1

    def test_normalize_issue_missing_date_defaults_now(self):
        raw = {
            "key": "no-date",
            "severity": "MAJOR",
            "type": "VULNERABILITY",
            "message": "Some issue",
            "component": "proj:file.java",
            "securityStandards": [],
        }
        before = datetime.now(timezone.utc)
        finding = SonarQubeAdapter._normalize_issue(raw)
        after = datetime.now(timezone.utc)
        assert before <= finding.detected_at <= after


class TestPullFindings:
    @pytest.mark.asyncio
    async def test_pull_findings_returns_normalized_list(self):
        """pull_findings with mocked HTTP returns list of NormalizedFindings."""
        endpoint = _make_endpoint()
        adapter = SonarQubeAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issues": [_raw_vulnerability_issue(), _raw_code_smell_issue()],
            "total": 2,
            "ps": 500,
            "p": 1,
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("pearl.integrations.adapters.sonarqube.httpx.AsyncClient", return_value=mock_client):
            findings = await adapter.pull_findings(endpoint, since=None)

        assert len(findings) == 2
        assert findings[0].source_tool == "sonarqube"
        assert findings[1].source_tool == "sonarqube"

    @pytest.mark.asyncio
    async def test_pull_findings_http_error_returns_empty(self):
        """HTTP errors should return an empty list, not raise."""
        import httpx

        endpoint = _make_endpoint()
        adapter = SonarQubeAdapter()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))

        with patch("pearl.integrations.adapters.sonarqube.httpx.AsyncClient", return_value=mock_client):
            findings = await adapter.pull_findings(endpoint, since=None)

        assert findings == []

    @pytest.mark.asyncio
    async def test_pull_findings_dedup_logic(self):
        """Calling pull_findings twice with same issues returns same external_ids (dedup is route-level).

        This test verifies that pull_findings always returns all current issues —
        dedup logic lives in the pull route which checks the DB for existing findings.
        """
        endpoint = _make_endpoint()
        adapter = SonarQubeAdapter()

        issues = [_raw_vulnerability_issue(), _raw_code_smell_issue()]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"issues": issues, "total": 2, "ps": 500, "p": 1}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("pearl.integrations.adapters.sonarqube.httpx.AsyncClient", return_value=mock_client):
            first_pull = await adapter.pull_findings(endpoint, since=None)
            second_pull = await adapter.pull_findings(endpoint, since=None)

        # Both calls return the same external_ids — dedup happens in route/worker
        first_ids = {f.external_id for f in first_pull}
        second_ids = {f.external_id for f in second_pull}
        assert first_ids == second_ids


class TestQualityGateStatus:
    @pytest.mark.asyncio
    async def test_quality_gate_status_ok(self):
        """get_quality_gate_status returns status=OK when SonarQube reports OK."""
        endpoint = _make_endpoint()
        adapter = SonarQubeAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "projectStatus": {
                "status": "OK",
                "conditions": [],
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("pearl.integrations.adapters.sonarqube.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.get_quality_gate_status(endpoint, "my-project")

        assert result["status"] == "OK"
        assert result["conditions"] == []

    @pytest.mark.asyncio
    async def test_quality_gate_status_error(self):
        """get_quality_gate_status returns status=ERROR when gate fails."""
        endpoint = _make_endpoint()
        adapter = SonarQubeAdapter()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "projectStatus": {
                "status": "ERROR",
                "conditions": [
                    {
                        "status": "ERROR",
                        "metricKey": "new_coverage",
                        "comparator": "LT",
                        "errorThreshold": "80",
                        "actualValue": "65.2",
                    }
                ],
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("pearl.integrations.adapters.sonarqube.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.get_quality_gate_status(endpoint, "my-project")

        assert result["status"] == "ERROR"
        assert len(result["conditions"]) == 1

    @pytest.mark.asyncio
    async def test_quality_gate_http_error_returns_unknown(self):
        """HTTP errors return UNKNOWN status, not raise."""
        import httpx

        endpoint = _make_endpoint()
        adapter = SonarQubeAdapter()

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))

        with patch("pearl.integrations.adapters.sonarqube.httpx.AsyncClient", return_value=mock_client):
            result = await adapter.get_quality_gate_status(endpoint, "my-project")

        assert result["status"] == "UNKNOWN"
