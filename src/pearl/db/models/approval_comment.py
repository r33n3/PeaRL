"""Approval conversation thread table."""

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base, TimestampMixin


class ApprovalCommentRow(Base, TimestampMixin):
    __tablename__ = "approval_comments"

    comment_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    approval_request_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("approval_requests.approval_request_id"), nullable=False, index=True
    )
    author: Mapped[str] = mapped_column(String(200), nullable=False)
    author_role: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    comment_type: Mapped[str] = mapped_column(String(50), nullable=False)  # question, evidence, note, decision_note
    attachments: Mapped[dict | None] = mapped_column(JSON, nullable=True)
