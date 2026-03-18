"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://pearl:pearl@localhost:5432/pearl"

    # Local development mode (set PEARL_LOCAL=1 to use SQLite, skip Redis)
    local_mode: bool = False

    local_reviewer_mode: bool = False

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # S3 / MinIO
    s3_endpoint_url: str = "http://localhost:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "pearl-artifacts"

    # JWT
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "pearl-api"
    jwt_audience: str = "pearl"
    jwt_private_key_path: str | None = None
    jwt_public_key_path: str | None = None
    jwt_access_token_expire_minutes: int = 60
    jwt_refresh_token_expire_days: int = 30

    # OIDC
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None

    # CORS
    cors_allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

    # Public-facing API URL — used when generating .pearl.yaml and .mcp.json for projects.
    # Set PEARL_PUBLIC_API_URL in your environment or .env so all generated configs point
    # to the correct host/port without any hardcoding.
    # Defaults to http://localhost:{port}/api/v1 when not set.
    public_api_url: str = ""

    @property
    def effective_public_api_url(self) -> str:
        if self.public_api_url:
            return self.public_api_url.rstrip("/")
        return f"http://localhost:{self.port}/api/v1"

    # OpenAPI schema exposure — defaults to True in local mode only
    # Set PEARL_EXPOSE_OPENAPI=1 to enable in production (not recommended)
    expose_openapi: bool | None = None

    @property
    def effective_expose_openapi(self) -> bool:
        if self.expose_openapi is not None:
            return self.expose_openapi
        return self.local_mode

    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_writes_per_minute: int = 100
    rate_limit_reads_per_minute: int = 1000

    # Audit HMAC (for immutable audit event signatures)
    audit_hmac_key: str = "dev-audit-hmac-key-change-in-production"

    # Slack
    slack_signing_secret: str = ""

    # Spec paths
    spec_dir: str = "PeaRL_spec"

    # Path to the pearl_dev src directory, used when generating .mcp.json for projects.
    # Defaults to auto-detected path relative to this file (works for dev installs).
    pearl_src_path: str = ""

    # MASS 2.0 integration
    mass_url: str = ""             # MASS 2.0 API base URL
    mass_api_key: str = ""         # MASS API key for authentication
    mass_scan_timeout: int = 600   # seconds to wait for MASS scan completion

    # AWS AgentCore — Cedar policy deployment
    # Credentials default to empty; boto3 falls back to IAM role / ~/.aws chain when unset.
    agentcore_gateway_arn: str = ""          # PEARL_AGENTCORE_GATEWAY_ARN
    agentcore_aws_region: str = "us-east-1"  # PEARL_AGENTCORE_AWS_REGION
    agentcore_aws_access_key_id: str = ""    # PEARL_AGENTCORE_AWS_ACCESS_KEY_ID
    agentcore_aws_secret_access_key: str = ""  # PEARL_AGENTCORE_AWS_SECRET_ACCESS_KEY
    agentcore_deploy_on_approval: bool = True  # PEARL_AGENTCORE_DEPLOY_ON_APPROVAL
    cedar_bundle_dry_run: bool = False         # PEARL_CEDAR_BUNDLE_DRY_RUN — generate but don't push

    # CloudWatch — AgentCore decision log bridge
    cloudwatch_log_group_arn: str = ""             # PEARL_CLOUDWATCH_LOG_GROUP_ARN
    cloudwatch_aws_region: str = "us-east-1"       # PEARL_CLOUDWATCH_AWS_REGION (may differ from AgentCore)
    cloudwatch_scan_interval_minutes: int = 60     # PEARL_CLOUDWATCH_SCAN_INTERVAL_MINUTES
    cloudwatch_scan_window_minutes: int = 60       # PEARL_CLOUDWATCH_SCAN_WINDOW_MINUTES
    cloudwatch_volume_anomaly_threshold: float = 3.0  # PEARL_CLOUDWATCH_VOLUME_ANOMALY_THRESHOLD (std devs)
    cloudwatch_query_timeout_seconds: int = 60     # PEARL_CLOUDWATCH_QUERY_TIMEOUT_SECONDS

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "PEARL_",
        "extra": "ignore",
    }

    @property
    def effective_database_url(self) -> str:
        """Return SQLite URL in local mode, PostgreSQL otherwise."""
        if self.local_mode:
            return "sqlite+aiosqlite:///pearl_local.db"
        return self.database_url


settings = Settings()
