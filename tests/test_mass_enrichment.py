"""Tests for MassClient enrichment methods."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from pearl.scanning.mass_bridge import MassClient


@pytest.mark.asyncio
async def test_get_verdict_returns_dict():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "risk_level": "high",
        "summary": "Test summary",
        "key_risks": ["risk1"],
        "immediate_actions": ["action1"],
        "confidence": 0.9,
        "finding_counts": {"total": 1, "high": 1},
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_verdict("scan-123")
    assert result["risk_level"] == "high"
    assert result["confidence"] == 0.9


@pytest.mark.asyncio
async def test_get_compliance_returns_dict():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "frameworks": {"owasp_llm": {"passed": True, "score": 1.0}},
        "overall_passed": True,
        "failed_controls": [],
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_compliance("scan-123")
    assert result["overall_passed"] is True


@pytest.mark.asyncio
async def test_get_policies_returns_list():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = [
        {"policy_type": "cedar", "content": {"statement": "permit(...);"} },
        {"policy_type": "bedrock", "content": {"topicPolicyConfig": {}}},
    ]
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_policies("scan-123")
    assert len(result) == 2
    assert result[0]["policy_type"] == "cedar"


@pytest.mark.asyncio
async def test_get_policies_normalizes_dict_response():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "cedar": {"statement": "permit(...);"},
        "bedrock": {"topicPolicyConfig": {}},
    }
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_policies("scan-123")
    assert len(result) == 2
    policy_types = {p["policy_type"] for p in result}
    assert policy_types == {"cedar", "bedrock"}
    assert result[0]["content"] is not None


@pytest.mark.asyncio
async def test_get_verdict_returns_empty_dict_on_404():
    client = MassClient(base_url="http://mass-test", api_key="key")
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock(status_code=404)
    )
    with patch.object(client._client, "get", new=AsyncMock(return_value=mock_response)):
        result = await client.get_verdict("scan-123")
    assert result == {}
