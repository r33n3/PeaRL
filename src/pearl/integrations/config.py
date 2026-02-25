"""Configuration models for external integration endpoints."""

import os

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import IntegrationCategory, IntegrationType


class AuthConfig(BaseModel):
    """Authentication config — stores env var NAMES, never actual secrets."""

    model_config = ConfigDict(extra="forbid")

    auth_type: str = "none"  # "api_key", "bearer", "basic", "oauth2", "none"
    api_key_env: str | None = None
    bearer_token_env: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    header_name: str | None = None  # Custom header for API key (default: Authorization)

    def resolve_api_key(self) -> str | None:
        """Resolve API key from environment variable."""
        if self.api_key_env:
            return os.environ.get(self.api_key_env)
        return None

    def resolve_bearer_token(self) -> str | None:
        """Resolve bearer token from environment variable."""
        if self.bearer_token_env:
            return os.environ.get(self.bearer_token_env)
        return None

    def resolve_basic_auth(self) -> tuple[str, str] | None:
        """Resolve basic auth credentials from environment variables."""
        if self.username_env and self.password_env:
            username = os.environ.get(self.username_env)
            password = os.environ.get(self.password_env)
            if username and password:
                return (username, password)
        return None

    def get_headers(self) -> dict[str, str]:
        """Build HTTP headers for authentication."""
        headers: dict[str, str] = {}
        if self.auth_type == "api_key":
            key = self.resolve_api_key()
            if key:
                header = self.header_name or "Authorization"
                headers[header] = key
        elif self.auth_type == "bearer":
            token = self.resolve_bearer_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers


class IntegrationEndpoint(BaseModel):
    """A configured external integration endpoint."""

    model_config = ConfigDict(extra="forbid")

    endpoint_id: str
    name: str
    adapter_type: str
    integration_type: IntegrationType
    category: IntegrationCategory
    base_url: str
    auth: AuthConfig = Field(default_factory=AuthConfig)
    project_mapping: dict[str, str] | None = None
    enabled: bool = True
    labels: dict[str, str] | None = None


class IntegrationRegistry(BaseModel):
    """Collection of all configured integration endpoints."""

    endpoints: list[IntegrationEndpoint] = Field(default_factory=list)

    def get_sources(self) -> list[IntegrationEndpoint]:
        """Get all enabled source endpoints."""
        return [
            e for e in self.endpoints
            if e.enabled and e.integration_type in (IntegrationType.SOURCE, IntegrationType.BIDIRECTIONAL)
        ]

    def get_sinks(self) -> list[IntegrationEndpoint]:
        """Get all enabled sink endpoints."""
        return [
            e for e in self.endpoints
            if e.enabled and e.integration_type in (IntegrationType.SINK, IntegrationType.BIDIRECTIONAL)
        ]

    def get_by_adapter(self, adapter_type: str) -> list[IntegrationEndpoint]:
        """Get all enabled endpoints for a specific adapter type."""
        return [
            e for e in self.endpoints
            if e.enabled and e.adapter_type == adapter_type
        ]

    def get_by_id(self, endpoint_id: str) -> IntegrationEndpoint | None:
        """Get endpoint by ID."""
        for e in self.endpoints:
            if e.endpoint_id == endpoint_id:
                return e
        return None
