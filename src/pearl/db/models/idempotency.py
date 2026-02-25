"""Idempotency key table."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base


class IdempotencyKeyRow(Base):
    __tablename__ = "idempotency_keys"

    key_hash: Mapped[str] = mapped_column(String(256), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
