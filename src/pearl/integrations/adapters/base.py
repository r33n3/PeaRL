"""Abstract base classes for source and sink adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from pearl.integrations.config import IntegrationEndpoint
from pearl.integrations.normalized import (
    NormalizedFinding,
    NormalizedNotification,
    NormalizedSecurityEvent,
    NormalizedTicket,
)


class SourceAdapter(ABC):
    """Pulls data from an external tool and converts to NormalizedFindings."""

    adapter_type: str = "unknown"

    @abstractmethod
    async def pull_findings(
        self,
        endpoint: IntegrationEndpoint,
        since: datetime | None = None,
    ) -> list[NormalizedFinding]:
        """Pull findings from the external source.

        Args:
            endpoint: The configured integration endpoint.
            since: Only return findings detected after this timestamp.

        Returns:
            List of normalized findings.
        """
        ...

    @abstractmethod
    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Test connectivity to the external source.

        Returns:
            True if connection is successful.
        """
        ...


class SinkAdapter(ABC):
    """Pushes PeaRL data to an external system."""

    adapter_type: str = "unknown"

    @abstractmethod
    async def push_event(
        self,
        endpoint: IntegrationEndpoint,
        event: NormalizedSecurityEvent,
    ) -> bool:
        """Push a security event to the sink.

        Returns:
            True if delivery succeeded.
        """
        ...

    async def push_ticket(
        self,
        endpoint: IntegrationEndpoint,
        ticket: NormalizedTicket,
    ) -> bool:
        """Push a ticket to the sink. Override in ticketing adapters."""
        raise NotImplementedError(f"{self.adapter_type} does not support tickets")

    async def push_notification(
        self,
        endpoint: IntegrationEndpoint,
        notification: NormalizedNotification,
    ) -> bool:
        """Push a notification to the sink. Override in notification adapters."""
        raise NotImplementedError(f"{self.adapter_type} does not support notifications")

    @abstractmethod
    async def test_connection(self, endpoint: IntegrationEndpoint) -> bool:
        """Test connectivity to the external sink."""
        ...
