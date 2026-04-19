"""Unit tests for LiteLLMAdapter pull_findings and test_connection."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from pearl.integrations.adapters.litellm import LiteLLMAdapter
from pearl.integrations.config import AuthConfig, IntegrationEndpoint
from pearl.integrations.litellm import ContractCompliance
from pearl.models.enums import IntegrationCategory, IntegrationType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_endpoint(
    key_aliases: str,
    raw_token: str = "sk-master",
) -> IntegrationEndpoint:
    return IntegrationEndpoint(
        endpoint_id="ep_test",
        name="Test LiteLLM",
        adapter_type="litellm",
        integration_type=IntegrationType.SOURCE,
        category=IntegrationCategory.AI_GOVERNANCE,
        base_url="http://litellm:4000",
        auth=AuthConfig(auth_type="bearer", raw_token=raw_token),
        labels={"key_aliases": key_aliases},
    )


def _make_compliance(violations: list[str]) -> ContractCompliance:
    return ContractCompliance(
        passed=len(violations) == 0,
        violations=violations,
        key_alias=None,
        actual_spend_usd=1.0,
        budget_cap_usd=10.0,
        actual_models_used=[],
        approved_models=[],
        request_count=1,
        checked_at="2024-01-01T00:00:00Z",
    )


# Real violation format strings from LiteLLMClient (matched by substring keywords).
# The adapter maps "budget" → high, "model" → medium, default → high.
_BUDGET_VIOLATION = "Budget exceeded: actual $11.0000 > cap $10.00"
_MODEL_VIOLATION = "Unauthorized model called: 'gpt-4' (allowed: [])"
_UNKNOWN_VIOLATION = "Unknown policy violation"


# ---------------------------------------------------------------------------
# pull_findings tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pull_findings_returns_empty_when_no_violations():
    endpoint = _make_endpoint(key_aliases="alias1")
    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        instance.get_key_compliance = AsyncMock(return_value=_make_compliance([]))
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)
    assert result == []


@pytest.mark.asyncio
async def test_pull_findings_maps_budget_violation_to_high_severity():
    endpoint = _make_endpoint(key_aliases="alias1")
    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        instance.get_key_compliance = AsyncMock(
            return_value=_make_compliance([_BUDGET_VIOLATION])
        )
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)

    assert len(result) == 1
    assert result[0].severity == "high"
    assert result[0].source_tool == "litellm"
    assert result[0].raw_record["actual_spend_usd"] == 1.0
    assert result[0].raw_record["budget_cap_usd"] == 10.0
    assert result[0].raw_record["key_alias"] == "alias1"


@pytest.mark.asyncio
async def test_pull_findings_maps_model_violation_to_medium_severity():
    endpoint = _make_endpoint(key_aliases="alias1")
    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        instance.get_key_compliance = AsyncMock(
            return_value=_make_compliance([_MODEL_VIOLATION])
        )
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)

    assert len(result) == 1
    assert result[0].severity == "medium"


@pytest.mark.asyncio
async def test_pull_findings_default_violation_is_high():
    endpoint = _make_endpoint(key_aliases="alias1")
    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        instance.get_key_compliance = AsyncMock(
            return_value=_make_compliance([_UNKNOWN_VIOLATION])
        )
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)

    assert len(result) == 1
    assert result[0].severity == "high"


@pytest.mark.asyncio
async def test_pull_findings_multiple_aliases_aggregates_findings():
    endpoint = _make_endpoint(key_aliases="alias1,alias2")
    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        instance.get_key_compliance = AsyncMock(
            return_value=_make_compliance([_BUDGET_VIOLATION])
        )
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)

    # get_key_compliance called once per alias
    assert instance.get_key_compliance.call_count == 2
    assert len(result) == 2


@pytest.mark.asyncio
async def test_pull_findings_unreachable_on_one_alias_continues_to_next():
    endpoint = _make_endpoint(key_aliases="alias1,alias2")

    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        instance.get_key_compliance = AsyncMock(
            side_effect=[
                httpx.ConnectError("Connection refused"),
                _make_compliance([_BUDGET_VIOLATION]),
            ]
        )
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)

    # alias1 failed, alias2 succeeded → 1 finding (continue, not return [])
    assert len(result) == 1


@pytest.mark.asyncio
async def test_pull_findings_http_error_on_alias_continues():
    endpoint = _make_endpoint(key_aliases="alias1,alias2")

    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        request = httpx.Request("GET", "http://litellm:4000/key/info")
        response = httpx.Response(503, request=request)
        instance.get_key_compliance = AsyncMock(
            side_effect=[
                httpx.HTTPStatusError("503", request=request, response=response),
                _make_compliance([_BUDGET_VIOLATION]),
            ]
        )
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)

    # alias1 failed with HTTPStatusError, alias2 succeeded → 1 finding
    assert len(result) == 1


@pytest.mark.asyncio
async def test_pull_findings_external_id_format():
    endpoint = _make_endpoint(key_aliases="alias1")

    with patch("pearl.integrations.litellm.LiteLLMClient") as MockClient:
        instance = MockClient.return_value
        instance.get_key_compliance = AsyncMock(
            return_value=_make_compliance([_BUDGET_VIOLATION, _MODEL_VIOLATION])
        )
        adapter = LiteLLMAdapter()
        result = await adapter.pull_findings(endpoint)

    assert len(result) == 2
    assert result[0].external_id == "litellm-alias1-0"
    assert result[1].external_id == "litellm-alias1-1"


# ---------------------------------------------------------------------------
# test_connection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_connection_returns_true_on_200():
    endpoint = _make_endpoint(key_aliases="alias1")
    adapter = LiteLLMAdapter()

    with patch.object(adapter, "_get_client") as mock_get_client:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=MagicMock(status_code=200))
        mock_get_client.return_value = mock_http

        result = await adapter.test_connection(endpoint)

    assert result is True
    mock_http.get.assert_called_once_with(
        "http://litellm:4000/health/liveliness",
        headers={"Authorization": "Bearer sk-master"},
        timeout=10.0,
    )


@pytest.mark.asyncio
async def test_test_connection_returns_false_on_non_200():
    endpoint = _make_endpoint(key_aliases="alias1")
    adapter = LiteLLMAdapter()

    with patch.object(adapter, "_get_client") as mock_get_client:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=MagicMock(status_code=503))
        mock_get_client.return_value = mock_http

        result = await adapter.test_connection(endpoint)

    assert result is False


@pytest.mark.asyncio
async def test_test_connection_returns_false_on_http_error():
    endpoint = _make_endpoint(key_aliases="alias1")
    adapter = LiteLLMAdapter()

    with patch.object(adapter, "_get_client") as mock_get_client:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=httpx.HTTPError("timeout"))
        mock_get_client.return_value = mock_http

        result = await adapter.test_connection(endpoint)

    assert result is False
