"""AllowanceProfile table — per-agent-type baseline enforcement rules."""

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class AllowanceProfileRow(Base, TimestampMixin):
    __tablename__ = "allowance_profiles"

    profile_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    agent_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Layer 1 — baseline rules
    blocked_commands: Mapped[list | None] = mapped_column(JSON, nullable=True)
    blocked_paths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    pre_approved_actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    model_restrictions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    budget_cap_usd: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Layer 2 — environment tier overrides keyed by tier name
    env_tier_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Optional project scope
    project_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("projects.project_id"), nullable=True, index=True
    )

    # Versioning — incremented on every update
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
