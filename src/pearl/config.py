"""Application configuration via environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://pearl:pearl@localhost:5432/pearl"

    # Local development mode (set PEARL_LOCAL=1 to use SQLite, skip Redis)
    local_mode: bool = False

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

    # Server
    host: str = "0.0.0.0"
    port: int = 8080
    log_level: str = "info"

    # Slack
    slack_signing_secret: str = ""

    # Spec paths
    spec_dir: str = "PeaRL_spec"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "PEARL_",
    }

    @property
    def effective_database_url(self) -> str:
        """Return SQLite URL in local mode, PostgreSQL otherwise."""
        if self.local_mode:
            return "sqlite+aiosqlite:///pearl_local.db"
        return self.database_url


settings = Settings()
