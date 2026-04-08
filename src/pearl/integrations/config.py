"""Configuration models for external integration endpoints."""

import os

from pydantic import BaseModel, ConfigDict, Field

from pearl.models.enums import IntegrationCategory, IntegrationType


class AuthConfig(BaseModel):
    """Authentication config for integration endpoints.

    Two modes:
    - **Env var (production)**: set ``bearer_token_env`` / ``api_key_env`` to the *name* of a
      server environment variable.  The secret is never stored in the database.
    - **Direct token (local / dev)**: set ``raw_token`` to the token value.  PeaRL stores it in
      the database.  Use env vars in production; only use ``raw_token`` on local instances where
      the database is not shared or persisted outside the development environment.

    No server restart is required for either mode — tokens are resolved at connection time.
    """

    model_config = ConfigDict(extra="forbid")

    auth_type: str = "none"  # "api_key", "bearer", "basic", "oauth2", "none"
    api_key_env: str | None = None
    bearer_token_env: str | None = None
    username_env: str | None = None
    password_env: str | None = None
    header_name: str | None = None  # Custom header for API key (default: Authorization)
    raw_token: str | None = None    # Direct token value — local/dev use only

    def resolve_api_key(self) -> str | None:
        """Resolve API key — env var first, raw_token as fallback."""
        if self.api_key_env:
            val = os.environ.get(self.api_key_env)
            if val:
                return val
        return self.raw_token or None

    def resolve_bearer_token(self) -> str | None:
        """Resolve bearer token — env var first, raw_token as fallback."""
        if self.bearer_token_env:
            val = os.environ.get(self.bearer_token_env)
            if val:
                return val
        return self.raw_token or None

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


# ---------------------------------------------------------------------------
# Integration Catalogue — static metadata for all supported adapter types.
# Used by the frontend integration picker and the ci-snippet endpoint to
# determine platform-appropriate CI YAML.
# ---------------------------------------------------------------------------

INTEGRATION_CATALOGUE: list[dict] = [
    {
        "adapter_type": "snyk",
        "integration_type": "source",
        "category": "sca",
        "name": "Snyk",
        "description": "Snyk SCA/SAST integration for dependency and code vulnerability scanning",
        "auth_types": ["api_key"],
        "labels_schema": {"org_id": "Snyk organization ID"},
    },
    {
        "adapter_type": "semgrep",
        "integration_type": "source",
        "category": "sast",
        "name": "Semgrep",
        "description": "Semgrep SAST integration for static analysis findings",
        "auth_types": ["api_key"],
        "labels_schema": {"deployment_id": "Semgrep deployment ID"},
    },
    {
        "adapter_type": "trivy",
        "integration_type": "source",
        "category": "container_scan",
        "name": "Trivy",
        "description": "Trivy container and IaC vulnerability scanner",
        "auth_types": ["none"],
        "labels_schema": {},
    },
    {
        "adapter_type": "sonarqube",
        "integration_type": "source",
        "category": "sast",
        "name": "SonarQube",
        "description": "SonarQube code quality and security analysis integration",
        "auth_types": ["api_key", "bearer"],
        "labels_schema": {"project_key": "SonarQube project key"},
    },
    {
        "adapter_type": "azure_devops",
        "integration_type": "ci_cd",
        "category": "ci_cd",
        "name": "Azure DevOps",
        "description": "Azure DevOps Pipelines CI/CD integration for automated gate scanning",
        "auth_types": ["pat"],
        "labels_schema": {
            "organization": "ADO org name",
            "project": "ADO project name",
        },
    },
    {
        "adapter_type": "jira",
        "integration_type": "sink",
        "category": "ticketing",
        "name": "Jira",
        "description": "Jira issue tracker integration for finding ticket creation",
        "auth_types": ["api_key", "basic"],
        "labels_schema": {"project_key": "Jira project key"},
    },
    {
        "adapter_type": "slack",
        "integration_type": "sink",
        "category": "notification",
        "name": "Slack",
        "description": "Slack notification integration for gate events and alerts",
        "auth_types": ["bearer"],
        "labels_schema": {"channel": "Default Slack channel"},
    },
    {
        "adapter_type": "github_issues",
        "integration_type": "sink",
        "category": "ticketing",
        "name": "GitHub Issues",
        "description": "GitHub Issues integration for finding ticket creation",
        "auth_types": ["bearer"],
        "labels_schema": {"repo": "owner/repo"},
    },
    {
        "adapter_type": "teams",
        "integration_type": "sink",
        "category": "notification",
        "name": "Microsoft Teams",
        "description": "Microsoft Teams webhook integration for gate notifications",
        "auth_types": ["none"],
        "labels_schema": {"webhook_url": "Teams incoming webhook URL"},
    },
    {
        "adapter_type": "telegram",
        "integration_type": "sink",
        "category": "notification",
        "name": "Telegram",
        "description": "Telegram bot integration for gate notifications",
        "auth_types": ["api_key"],
        "labels_schema": {"chat_id": "Telegram chat ID"},
    },
    {
        "adapter_type": "webhook",
        "integration_type": "sink",
        "category": "notification",
        "name": "Webhook",
        "description": "Generic outbound webhook for custom integrations",
        "auth_types": ["api_key", "bearer", "none"],
        "labels_schema": {"url": "Webhook target URL"},
    },
    {
        "adapter_type": "mass",
        "integration_type": "source",
        "category": "dast",
        "name": "MASS 2.0",
        "description": "AI deployment security scanner — scans agent deployments for security and governance risks",
        "auth_types": ["bearer", "none"],
        "labels_schema": {},
    },
]
