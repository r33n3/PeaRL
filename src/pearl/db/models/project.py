"""Project table."""

from sqlalchemy import JSON, Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ProjectRow(Base, TimestampMixin):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_team: Mapped[str] = mapped_column(String(200), nullable=False)
    business_criticality: Mapped[str] = mapped_column(String(50), nullable=False)
    external_exposure: Mapped[str] = mapped_column(String(50), nullable=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.1")
    org_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    bu_id: Mapped[str | None] = mapped_column(
        String(128), ForeignKey("business_units.bu_id"), nullable=True, index=True
    )
    current_environment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    claude_md_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ── Dark Factory governance container fields ──────────────────────────
    intake_card_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    goal_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    target_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    risk_classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_members: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    litellm_key_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    memory_policy_refs: Mapped[list | None] = mapped_column(JSON, nullable=True)
    qualification_packet_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
