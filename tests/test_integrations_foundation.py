"""Comprehensive tests for the integration framework foundation.

Covers:
- pearl.models.enums (IntegrationType, IntegrationCategory, AdapterStatus)
- pearl.integrations.config (AuthConfig, IntegrationEndpoint, IntegrationRegistry)
- pearl.integrations.normalized (NormalizedFinding, NormalizedSecurityEvent,
  NormalizedTicket, NormalizedNotification)
- pearl.integrations.bridge (normalized_to_finding, normalized_to_batch,
  finding_to_security_event, finding_to_ticket, finding_to_notification)
- pearl.integrations.adapters (AVAILABLE_ADAPTERS, import_adapter)
"""

from datetime import datetime, timezone

import pytest

from pearl.models.enums import AdapterStatus, IntegrationCategory, IntegrationType
from pearl.integrations.config import AuthConfig, IntegrationEndpoint, IntegrationRegistry
from pearl.integrations.normalized import (
    NormalizedFinding,
    NormalizedNotification,
    NormalizedSecurityEvent,
    NormalizedTicket,
)
from pearl.integrations.bridge import (
    finding_to_notification,
    finding_to_security_event,
    finding_to_ticket,
    normalized_to_batch,
    normalized_to_finding,
)
from pearl.integrations.adapters import AVAILABLE_ADAPTERS, import_adapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_normalized_finding() -> NormalizedFinding:
    """A minimal NormalizedFinding suitable for most bridge tests."""
    return NormalizedFinding(
        external_id="SNYK-JS-LODASH-1234",
        source_tool="snyk",
        source_type="sca",
        title="Prototype Pollution in lodash",
        description="lodash before 4.17.21 is vulnerable to prototype pollution.",
        severity="high",
        confidence="high",
        category="security",
        affected_components=["lodash@4.17.20"],
        cwe_ids=["CWE-1321"],
        cve_id="CVE-2021-23337",
        cvss_score=7.4,
        fix_available=True,
        detected_at=datetime(2026, 2, 20, 12, 0, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_pearl_finding() -> dict:
    """A PeaRL Finding dict in the canonical ingest format."""
    return {
        "finding_id": "find_test_001",
        "source": {
            "tool_name": "snyk",
            "tool_type": "sca",
            "connector_id": None,
            "trust_label": "trusted_external_registered",
            "raw_record_ref": "SNYK-JS-LODASH-1234",
        },
        "project_id": "proj_acme_api",
        "environment": "dev",
        "category": "security",
        "severity": "high",
        "confidence": "high",
        "title": "Prototype Pollution in lodash",
        "description": "lodash before 4.17.21 is vulnerable.",
        "affected_components": ["lodash@4.17.20"],
        "cwe_ids": ["CWE-1321"],
        "cve_id": "CVE-2021-23337",
        "cvss_score": 7.4,
        "fix_available": True,
        "compliance_refs": {},
        "detected_at": "2026-02-20T12:00:00+00:00",
        "status": "open",
    }


def _make_endpoint(
    endpoint_id: str = "ep_snyk_01",
    name: str = "Snyk SCA",
    adapter_type: str = "snyk",
    integration_type: IntegrationType = IntegrationType.SOURCE,
    category: IntegrationCategory = IntegrationCategory.SCA,
    base_url: str = "https://api.snyk.io",
    enabled: bool = True,
    **kwargs,
) -> IntegrationEndpoint:
    """Helper to build an IntegrationEndpoint with sensible defaults."""
    return IntegrationEndpoint(
        endpoint_id=endpoint_id,
        name=name,
        adapter_type=adapter_type,
        integration_type=integration_type,
        category=category,
        base_url=base_url,
        enabled=enabled,
        **kwargs,
    )


# =========================================================================
# 1. Enum tests
# =========================================================================


class TestIntegrationEnums:
    """Tests for IntegrationType, IntegrationCategory, and AdapterStatus."""

    def test_integration_type_values(self):
        assert IntegrationType.SOURCE == "source"
        assert IntegrationType.SINK == "sink"
        assert IntegrationType.BIDIRECTIONAL == "bidirectional"

    def test_integration_type_membership(self):
        assert "source" in [e.value for e in IntegrationType]
        assert "sink" in [e.value for e in IntegrationType]
        assert "bidirectional" in [e.value for e in IntegrationType]

    def test_integration_category_has_expected_values(self):
        expected = {
            "sast", "dast", "sca", "container_scan", "cloud_posture",
            "secrets_scan", "siem", "ticketing", "notification", "ci_cd",
            "git_platform", "vulnerability_feed", "policy_engine",
        }
        actual = {e.value for e in IntegrationCategory}
        assert expected == actual

    def test_adapter_status_values(self):
        assert AdapterStatus.ACTIVE == "active"
        assert AdapterStatus.DISABLED == "disabled"
        assert AdapterStatus.ERROR == "error"
        assert AdapterStatus.PENDING_AUTH == "pending_auth"

    def test_enums_are_string_comparable(self):
        """StrEnum members should compare equal to their string values."""
        assert IntegrationType.SOURCE == "source"
        assert IntegrationCategory.SIEM == "siem"
        assert AdapterStatus.ACTIVE == "active"


# =========================================================================
# 2. AuthConfig tests
# =========================================================================


class TestAuthConfig:
    """Tests for AuthConfig: resolve_api_key, resolve_bearer_token, get_headers."""

    def test_default_auth_type_is_none(self):
        auth = AuthConfig()
        assert auth.auth_type == "none"

    def test_resolve_api_key_returns_env_value(self, monkeypatch):
        monkeypatch.setenv("MY_SNYK_KEY", "sk-test-12345")
        auth = AuthConfig(auth_type="api_key", api_key_env="MY_SNYK_KEY")
        assert auth.resolve_api_key() == "sk-test-12345"

    def test_resolve_api_key_returns_none_when_env_missing(self, monkeypatch):
        monkeypatch.delenv("NONEXISTENT_KEY_VAR", raising=False)
        auth = AuthConfig(auth_type="api_key", api_key_env="NONEXISTENT_KEY_VAR")
        assert auth.resolve_api_key() is None

    def test_resolve_api_key_returns_none_when_no_env_var_configured(self):
        auth = AuthConfig(auth_type="api_key")
        assert auth.resolve_api_key() is None

    def test_resolve_bearer_token(self, monkeypatch):
        monkeypatch.setenv("JIRA_TOKEN", "bearer-abc-789")
        auth = AuthConfig(auth_type="bearer", bearer_token_env="JIRA_TOKEN")
        assert auth.resolve_bearer_token() == "bearer-abc-789"

    def test_get_headers_api_key_default_header(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "key-value")
        auth = AuthConfig(auth_type="api_key", api_key_env="API_KEY")
        headers = auth.get_headers()
        assert headers == {"Authorization": "key-value"}

    def test_get_headers_api_key_custom_header(self, monkeypatch):
        monkeypatch.setenv("API_KEY", "key-value")
        auth = AuthConfig(
            auth_type="api_key",
            api_key_env="API_KEY",
            header_name="X-Api-Key",
        )
        headers = auth.get_headers()
        assert headers == {"X-Api-Key": "key-value"}

    def test_get_headers_bearer(self, monkeypatch):
        monkeypatch.setenv("BEARER_TOK", "tok-999")
        auth = AuthConfig(auth_type="bearer", bearer_token_env="BEARER_TOK")
        headers = auth.get_headers()
        assert headers == {"Authorization": "Bearer tok-999"}

    def test_get_headers_returns_empty_for_none_auth(self):
        auth = AuthConfig(auth_type="none")
        assert auth.get_headers() == {}

    def test_get_headers_returns_empty_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        auth = AuthConfig(auth_type="api_key", api_key_env="MISSING_VAR")
        assert auth.get_headers() == {}


# =========================================================================
# 3. IntegrationEndpoint tests
# =========================================================================


class TestIntegrationEndpoint:
    """Tests for IntegrationEndpoint model validation and defaults."""

    def test_minimal_construction(self):
        ep = _make_endpoint()
        assert ep.endpoint_id == "ep_snyk_01"
        assert ep.enabled is True
        assert ep.auth.auth_type == "none"

    def test_project_mapping_optional(self):
        ep = _make_endpoint(project_mapping={"proj_acme": "snyk-org-123"})
        assert ep.project_mapping["proj_acme"] == "snyk-org-123"

    def test_labels_optional(self):
        ep = _make_endpoint(labels={"team": "security"})
        assert ep.labels["team"] == "security"


# =========================================================================
# 4. IntegrationRegistry tests
# =========================================================================


class TestIntegrationRegistry:
    """Tests for IntegrationRegistry: get_sources, get_sinks, get_by_adapter, get_by_id."""

    @pytest.fixture
    def registry(self) -> IntegrationRegistry:
        return IntegrationRegistry(endpoints=[
            _make_endpoint(
                endpoint_id="ep_snyk",
                adapter_type="snyk",
                integration_type=IntegrationType.SOURCE,
                category=IntegrationCategory.SCA,
            ),
            _make_endpoint(
                endpoint_id="ep_jira",
                name="Jira Cloud",
                adapter_type="jira",
                integration_type=IntegrationType.SINK,
                category=IntegrationCategory.TICKETING,
                base_url="https://acme.atlassian.net",
            ),
            _make_endpoint(
                endpoint_id="ep_github",
                name="GitHub Issues",
                adapter_type="github_issues",
                integration_type=IntegrationType.BIDIRECTIONAL,
                category=IntegrationCategory.GIT_PLATFORM,
                base_url="https://api.github.com",
            ),
            _make_endpoint(
                endpoint_id="ep_disabled",
                name="Disabled endpoint",
                adapter_type="slack",
                integration_type=IntegrationType.SINK,
                category=IntegrationCategory.NOTIFICATION,
                base_url="https://hooks.slack.com",
                enabled=False,
            ),
        ])

    def test_get_sources_returns_source_and_bidirectional(self, registry):
        sources = registry.get_sources()
        ids = {s.endpoint_id for s in sources}
        assert "ep_snyk" in ids
        assert "ep_github" in ids  # bidirectional counts as a source
        assert "ep_jira" not in ids  # pure sink excluded

    def test_get_sinks_returns_sink_and_bidirectional(self, registry):
        sinks = registry.get_sinks()
        ids = {s.endpoint_id for s in sinks}
        assert "ep_jira" in ids
        assert "ep_github" in ids  # bidirectional counts as a sink
        assert "ep_snyk" not in ids  # pure source excluded

    def test_get_sources_excludes_disabled(self, registry):
        sources = registry.get_sources()
        ids = {s.endpoint_id for s in sources}
        assert "ep_disabled" not in ids

    def test_get_sinks_excludes_disabled(self, registry):
        sinks = registry.get_sinks()
        ids = {s.endpoint_id for s in sinks}
        assert "ep_disabled" not in ids

    def test_get_by_adapter(self, registry):
        jira_endpoints = registry.get_by_adapter("jira")
        assert len(jira_endpoints) == 1
        assert jira_endpoints[0].endpoint_id == "ep_jira"

    def test_get_by_adapter_empty(self, registry):
        assert registry.get_by_adapter("nonexistent") == []

    def test_get_by_id_found(self, registry):
        ep = registry.get_by_id("ep_snyk")
        assert ep is not None
        assert ep.adapter_type == "snyk"

    def test_get_by_id_not_found(self, registry):
        assert registry.get_by_id("ep_does_not_exist") is None

    def test_empty_registry(self):
        reg = IntegrationRegistry()
        assert reg.get_sources() == []
        assert reg.get_sinks() == []
        assert reg.get_by_adapter("snyk") == []
        assert reg.get_by_id("any") is None


# =========================================================================
# 5. Normalized model tests
# =========================================================================


class TestNormalizedModels:
    """Tests for NormalizedFinding, NormalizedSecurityEvent, NormalizedTicket,
    NormalizedNotification construction and validation."""

    def test_normalized_finding_construction(self, sample_normalized_finding):
        nf = sample_normalized_finding
        assert nf.external_id == "SNYK-JS-LODASH-1234"
        assert nf.severity == "high"
        assert nf.cvss_score == 7.4
        assert nf.detected_at.year == 2026

    def test_normalized_finding_minimal(self):
        nf = NormalizedFinding(
            external_id="ext-001",
            source_tool="trivy",
            source_type="container_scan",
            title="Vulnerable base image",
            severity="critical",
            detected_at=datetime.now(timezone.utc),
        )
        assert nf.description is None
        assert nf.cve_id is None
        assert nf.fix_available is None
        assert nf.category == "security"

    def test_normalized_finding_cvss_score_range(self):
        """CVSS score must be between 0.0 and 10.0."""
        with pytest.raises(Exception):  # pydantic ValidationError
            NormalizedFinding(
                external_id="bad",
                source_tool="snyk",
                source_type="sca",
                title="Bad score",
                severity="low",
                detected_at=datetime.now(timezone.utc),
                cvss_score=15.0,
            )

    def test_normalized_security_event(self):
        event = NormalizedSecurityEvent(
            event_type="finding_created",
            severity="high",
            timestamp=datetime.now(timezone.utc),
            project_id="proj_test",
            summary="[HIGH] Test finding",
        )
        assert event.event_type == "finding_created"
        assert event.details == {}

    def test_normalized_ticket(self):
        ticket = NormalizedTicket(
            title="[HIGH] Fix lodash",
            description="Upgrade lodash",
            priority="high",
            labels=["security", "severity:high"],
            finding_ids=["find_001"],
            project_id="proj_test",
        )
        assert ticket.priority == "high"
        assert "security" in ticket.labels

    def test_normalized_notification(self):
        notif = NormalizedNotification(
            subject="[PeaRL] CRITICAL finding",
            body="A critical finding was detected.",
            severity="critical",
            project_id="proj_test",
        )
        assert notif.channel is None
        assert notif.finding_ids is None


# =========================================================================
# 6. Bridge: normalized_to_finding
# =========================================================================


class TestNormalizedToFinding:
    """Tests for bridge.normalized_to_finding()."""

    def test_produces_finding_dict_with_correct_keys(self, sample_normalized_finding):
        result = normalized_to_finding(sample_normalized_finding, "proj_acme")
        expected_keys = {
            "finding_id", "source", "project_id", "environment", "category",
            "severity", "confidence", "title", "description",
            "affected_components", "cwe_ids", "cve_id", "cvss_score",
            "fix_available", "compliance_refs", "detected_at", "status",
        }
        assert expected_keys == set(result.keys())

    def test_source_sub_dict_structure(self, sample_normalized_finding):
        result = normalized_to_finding(sample_normalized_finding, "proj_acme")
        src = result["source"]
        assert src["tool_name"] == "snyk"
        assert src["tool_type"] == "sca"
        assert src["trust_label"] == "trusted_external_registered"
        assert src["raw_record_ref"] == "SNYK-JS-LODASH-1234"

    def test_severity_mapping_medium_to_moderate(self):
        nf = NormalizedFinding(
            external_id="ext-1",
            source_tool="semgrep",
            source_type="sast",
            title="Medium severity issue",
            severity="medium",
            detected_at=datetime.now(timezone.utc),
        )
        result = normalized_to_finding(nf, "proj_x")
        assert result["severity"] == "moderate"

    def test_severity_mapping_critical_stays_critical(self):
        nf = NormalizedFinding(
            external_id="ext-2",
            source_tool="trivy",
            source_type="container_scan",
            title="Critical CVE",
            severity="critical",
            detected_at=datetime.now(timezone.utc),
        )
        result = normalized_to_finding(nf, "proj_x")
        assert result["severity"] == "critical"

    def test_severity_mapping_info_to_low(self):
        nf = NormalizedFinding(
            external_id="ext-3",
            source_tool="trivy",
            source_type="container_scan",
            title="Info finding",
            severity="info",
            detected_at=datetime.now(timezone.utc),
        )
        result = normalized_to_finding(nf, "proj_x")
        assert result["severity"] == "low"

    def test_custom_finding_id_passed_through(self, sample_normalized_finding):
        result = normalized_to_finding(
            sample_normalized_finding,
            "proj_acme",
            finding_id="find_custom_001",
        )
        assert result["finding_id"] == "find_custom_001"

    def test_auto_generated_finding_id(self, sample_normalized_finding):
        result = normalized_to_finding(sample_normalized_finding, "proj_acme")
        assert result["finding_id"].startswith("find_")

    def test_environment_defaults_to_dev(self, sample_normalized_finding):
        result = normalized_to_finding(sample_normalized_finding, "proj_acme")
        assert result["environment"] == "dev"

    def test_environment_override(self, sample_normalized_finding):
        result = normalized_to_finding(
            sample_normalized_finding, "proj_acme", environment="preprod"
        )
        assert result["environment"] == "preprod"

    def test_endpoint_id_passed_to_connector_id(self, sample_normalized_finding):
        result = normalized_to_finding(
            sample_normalized_finding, "proj_acme", endpoint_id="ep_snyk_01"
        )
        assert result["source"]["connector_id"] == "ep_snyk_01"

    def test_status_is_open(self, sample_normalized_finding):
        result = normalized_to_finding(sample_normalized_finding, "proj_acme")
        assert result["status"] == "open"


# =========================================================================
# 7. Bridge: normalized_to_batch
# =========================================================================


class TestNormalizedToBatch:
    """Tests for bridge.normalized_to_batch()."""

    def test_batch_structure(self, sample_normalized_finding):
        batch = normalized_to_batch([sample_normalized_finding], "proj_acme")
        assert "schema_version" in batch
        assert "source_batch" in batch
        assert "findings" in batch
        assert "options" in batch

    def test_batch_contains_all_findings(self, sample_normalized_finding):
        nf2 = NormalizedFinding(
            external_id="ext-2",
            source_tool="trivy",
            source_type="container_scan",
            title="Second finding",
            severity="low",
            detected_at=datetime.now(timezone.utc),
        )
        batch = normalized_to_batch([sample_normalized_finding, nf2], "proj_acme")
        assert len(batch["findings"]) == 2

    def test_batch_source_system_combines_tool_names(self):
        nf1 = NormalizedFinding(
            external_id="ext-a",
            source_tool="snyk",
            source_type="sca",
            title="A",
            severity="low",
            detected_at=datetime.now(timezone.utc),
        )
        nf2 = NormalizedFinding(
            external_id="ext-b",
            source_tool="trivy",
            source_type="container_scan",
            title="B",
            severity="low",
            detected_at=datetime.now(timezone.utc),
        )
        batch = normalized_to_batch([nf1, nf2], "proj_acme")
        # Sorted alphabetically: snyk_trivy
        assert batch["source_batch"]["source_system"] == "snyk_trivy"


# =========================================================================
# 8. Bridge: finding_to_security_event
# =========================================================================


class TestFindingToSecurityEvent:
    """Tests for bridge.finding_to_security_event()."""

    def test_returns_normalized_security_event(self, sample_pearl_finding):
        event = finding_to_security_event(sample_pearl_finding)
        assert isinstance(event, NormalizedSecurityEvent)

    def test_event_type_default(self, sample_pearl_finding):
        event = finding_to_security_event(sample_pearl_finding)
        assert event.event_type == "finding_created"

    def test_event_type_custom(self, sample_pearl_finding):
        event = finding_to_security_event(sample_pearl_finding, event_type="gate_passed")
        assert event.event_type == "gate_passed"

    def test_summary_contains_severity(self, sample_pearl_finding):
        event = finding_to_security_event(sample_pearl_finding)
        assert "HIGH" in event.summary

    def test_finding_ids_populated(self, sample_pearl_finding):
        event = finding_to_security_event(sample_pearl_finding)
        assert event.finding_ids == ["find_test_001"]


# =========================================================================
# 9. Bridge: finding_to_ticket
# =========================================================================


class TestFindingToTicket:
    """Tests for bridge.finding_to_ticket()."""

    def test_returns_normalized_ticket(self, sample_pearl_finding):
        ticket = finding_to_ticket(sample_pearl_finding)
        assert isinstance(ticket, NormalizedTicket)

    def test_ticket_title_includes_severity(self, sample_pearl_finding):
        ticket = finding_to_ticket(sample_pearl_finding)
        assert "[HIGH]" in ticket.title

    def test_ticket_title_includes_project_name(self, sample_pearl_finding):
        ticket = finding_to_ticket(sample_pearl_finding, project_name="Acme API")
        assert "Acme API" in ticket.title

    def test_priority_mapping_high(self, sample_pearl_finding):
        ticket = finding_to_ticket(sample_pearl_finding)
        assert ticket.priority == "high"

    def test_priority_mapping_critical(self, sample_pearl_finding):
        sample_pearl_finding["severity"] = "critical"
        ticket = finding_to_ticket(sample_pearl_finding)
        assert ticket.priority == "critical"

    def test_priority_mapping_moderate_to_medium(self, sample_pearl_finding):
        sample_pearl_finding["severity"] = "moderate"
        ticket = finding_to_ticket(sample_pearl_finding)
        assert ticket.priority == "medium"

    def test_labels_include_severity_tag(self, sample_pearl_finding):
        ticket = finding_to_ticket(sample_pearl_finding)
        assert "severity:high" in ticket.labels
        assert "security" in ticket.labels

    def test_labels_include_category(self, sample_pearl_finding):
        sample_pearl_finding["category"] = "responsible_ai"
        ticket = finding_to_ticket(sample_pearl_finding)
        assert "responsible_ai" in ticket.labels


# =========================================================================
# 10. Bridge: finding_to_notification
# =========================================================================


class TestFindingToNotification:
    """Tests for bridge.finding_to_notification()."""

    def test_returns_notification_when_above_threshold(self, sample_pearl_finding):
        notif = finding_to_notification(sample_pearl_finding, severity_threshold="high")
        assert notif is not None
        assert isinstance(notif, NormalizedNotification)

    def test_returns_none_when_below_threshold(self, sample_pearl_finding):
        sample_pearl_finding["severity"] = "low"
        notif = finding_to_notification(sample_pearl_finding, severity_threshold="high")
        assert notif is None

    def test_moderate_below_high_threshold(self, sample_pearl_finding):
        sample_pearl_finding["severity"] = "moderate"
        notif = finding_to_notification(sample_pearl_finding, severity_threshold="high")
        assert notif is None

    def test_critical_above_high_threshold(self, sample_pearl_finding):
        sample_pearl_finding["severity"] = "critical"
        notif = finding_to_notification(sample_pearl_finding, severity_threshold="high")
        assert notif is not None

    def test_notification_subject_contains_severity(self, sample_pearl_finding):
        notif = finding_to_notification(sample_pearl_finding, severity_threshold="low")
        assert notif is not None
        assert "HIGH" in notif.subject

    def test_notification_body_contains_finding_id(self, sample_pearl_finding):
        notif = finding_to_notification(sample_pearl_finding, severity_threshold="low")
        assert notif is not None
        assert "find_test_001" in notif.body


# =========================================================================
# 11. Adapter registry tests
# =========================================================================


class TestAdapterRegistry:
    """Tests for AVAILABLE_ADAPTERS and import_adapter."""

    def test_available_adapters_contains_expected_keys(self):
        expected = {"snyk", "semgrep", "trivy", "jira", "slack", "github_issues"}
        assert expected == set(AVAILABLE_ADAPTERS.keys())

    def test_available_adapters_values_are_dotted_paths(self):
        for name, path in AVAILABLE_ADAPTERS.items():
            parts = path.rsplit(".", 1)
            assert len(parts) == 2, f"Expected dotted class path for {name}, got {path}"
            assert parts[1][0].isupper(), f"Class name should be capitalized for {name}"

    def test_import_adapter_with_known_module(self):
        """import_adapter should be able to import the base SourceAdapter class."""
        cls = import_adapter("pearl.integrations.adapters.base.SourceAdapter")
        assert cls.__name__ == "SourceAdapter"

    def test_import_adapter_raises_on_bad_path(self):
        with pytest.raises((ModuleNotFoundError, AttributeError)):
            import_adapter("pearl.integrations.adapters.nonexistent.FakeAdapter")
