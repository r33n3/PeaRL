"""IntegrationService — orchestrates pulling from sources and pushing to sinks."""

from __future__ import annotations

import logging
from datetime import datetime

from pearl.integrations.adapters import AVAILABLE_ADAPTERS, import_adapter
from pearl.integrations.adapters.base import SinkAdapter, SourceAdapter
from pearl.integrations.bridge import normalized_to_batch
from pearl.integrations.config import IntegrationEndpoint, IntegrationRegistry
from pearl.integrations.normalized import (
    NormalizedNotification,
    NormalizedSecurityEvent,
    NormalizedTicket,
)

logger = logging.getLogger(__name__)


class IntegrationService:
    """Orchestrates external integration operations."""

    def __init__(self, registry: IntegrationRegistry):
        self.registry = registry
        self._adapters: dict[str, SourceAdapter | SinkAdapter] = {}

    async def pull_from_source(
        self,
        endpoint_id: str,
        project_id: str,
        environment: str = "dev",
        since: datetime | None = None,
    ) -> dict:
        """Pull findings from a source, normalize, and convert to PeaRL format.

        Returns:
            Dict with keys: endpoint_id, findings_count, batch (PeaRL ingest format)
        """
        endpoint = self.registry.get_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint not found: {endpoint_id}")

        adapter = self._get_source_adapter(endpoint.adapter_type)
        normalized = await adapter.pull_findings(endpoint, since)

        batch = normalized_to_batch(
            normalized,
            project_id=project_id,
            environment=environment,
            endpoint_id=endpoint_id,
        )

        logger.info(
            "Pulled %d findings from %s (%s)",
            len(normalized), endpoint.name, endpoint.adapter_type,
        )

        return {
            "endpoint_id": endpoint_id,
            "endpoint_name": endpoint.name,
            "findings_count": len(normalized),
            "batch": batch,
        }

    async def push_to_sinks(
        self,
        event: NormalizedSecurityEvent,
    ) -> list[dict]:
        """Fan out a security event to all enabled sink endpoints.

        Returns:
            List of delivery results per sink.
        """
        sinks = self.registry.get_sinks()
        results = []

        for endpoint in sinks:
            try:
                adapter = self._get_sink_adapter(endpoint.adapter_type)
                success = await adapter.push_event(endpoint, event)
                results.append({
                    "endpoint_id": endpoint.endpoint_id,
                    "endpoint_name": endpoint.name,
                    "status": "delivered" if success else "failed",
                })
            except Exception as exc:
                logger.warning(
                    "Failed to push event to %s: %s", endpoint.name, exc,
                )
                results.append({
                    "endpoint_id": endpoint.endpoint_id,
                    "endpoint_name": endpoint.name,
                    "status": "error",
                    "error": str(exc),
                })

        return results

    async def push_ticket(
        self,
        endpoint_id: str,
        ticket: NormalizedTicket,
    ) -> dict:
        """Push a ticket to a specific sink endpoint."""
        endpoint = self.registry.get_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint not found: {endpoint_id}")

        adapter = self._get_sink_adapter(endpoint.adapter_type)
        success = await adapter.push_ticket(endpoint, ticket)
        return {
            "endpoint_id": endpoint_id,
            "status": "delivered" if success else "failed",
        }

    async def push_notification(
        self,
        endpoint_id: str,
        notification: NormalizedNotification,
    ) -> dict:
        """Push a notification to a specific sink endpoint."""
        endpoint = self.registry.get_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint not found: {endpoint_id}")

        adapter = self._get_sink_adapter(endpoint.adapter_type)
        success = await adapter.push_notification(endpoint, notification)
        return {
            "endpoint_id": endpoint_id,
            "status": "delivered" if success else "failed",
        }

    async def test_endpoint(self, endpoint_id: str) -> dict:
        """Test connectivity to an endpoint.

        Returns:
            Dict with endpoint_id, name, status, and optional error.
        """
        endpoint = self.registry.get_by_id(endpoint_id)
        if not endpoint:
            raise ValueError(f"Endpoint not found: {endpoint_id}")

        try:
            adapter = self._get_adapter(endpoint.adapter_type)
            success = await adapter.test_connection(endpoint)
            return {
                "endpoint_id": endpoint_id,
                "endpoint_name": endpoint.name,
                "status": "connected" if success else "failed",
            }
        except Exception as exc:
            return {
                "endpoint_id": endpoint_id,
                "endpoint_name": endpoint.name,
                "status": "error",
                "error": str(exc),
            }

    def _get_adapter(self, adapter_type: str) -> SourceAdapter | SinkAdapter:
        """Get or lazy-load an adapter by type."""
        if adapter_type not in self._adapters:
            dotted = AVAILABLE_ADAPTERS.get(adapter_type)
            if not dotted:
                raise ValueError(f"Unknown adapter type: {adapter_type}")
            cls = import_adapter(dotted)
            self._adapters[adapter_type] = cls()
        return self._adapters[adapter_type]

    def _get_source_adapter(self, adapter_type: str) -> SourceAdapter:
        """Get a source adapter, raising if it's not a SourceAdapter."""
        adapter = self._get_adapter(adapter_type)
        if not isinstance(adapter, SourceAdapter):
            raise TypeError(f"Adapter {adapter_type} is not a SourceAdapter")
        return adapter

    def _get_sink_adapter(self, adapter_type: str) -> SinkAdapter:
        """Get a sink adapter, raising if it's not a SinkAdapter."""
        adapter = self._get_adapter(adapter_type)
        if not isinstance(adapter, SinkAdapter):
            raise TypeError(f"Adapter {adapter_type} is not a SinkAdapter")
        return adapter
