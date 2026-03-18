"""Cedar policy deployment tracking — one row per bundle deployed to AgentCore."""

from sqlalchemy import JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class CedarDeploymentRow(Base, TimestampMixin):
    """Tracks every Cedar policy bundle PeaRL has generated and deployed.

    The ``bundle_hash`` (SHA-256 of canonical JSON) is the key used by the
    CloudWatch bridge to detect policy drift: if AgentCore logs show a
    different hash than the latest ``active`` row, Cedar was modified
    outside PeaRL's governance workflow.
    """

    __tablename__ = "cedar_deployments"

    deployment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # AgentCore gateway this bundle was pushed to
    gateway_arn: Mapped[str] = mapped_column(String(512), nullable=False)

    # SHA-256 of the canonical JSON bundle — used for drift detection
    bundle_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Full Cedar bundle stored inline (bundles are typically <100 KB)
    bundle_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Lifecycle: active | pending | failed | superseded
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending")

    # Who / what initiated this deployment
    deployed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False)  # approval | manual | scheduler
    approval_id: Mapped[str | None] = mapped_column(String(128), nullable=True)   # soft ref
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Response from AgentCore after deploy
    agentcore_deployment_id: Mapped[str | None] = mapped_column(String(256), nullable=True)

    # Populated on failure
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
