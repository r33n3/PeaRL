"""Pydantic model for WebhookEnvelope entity."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class WebhookEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(..., pattern=r"^\d+\.\d+(\.\d+)?$")
    event_type: str
    event_id: str
    occurred_at: datetime
    source_system: str
    signature: str | None = None
    payload: dict[str, Any]
