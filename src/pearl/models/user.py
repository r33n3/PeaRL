"""Pydantic models for user and authentication."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


# ── Request models ─────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8)
    roles: list[str] = Field(default=["viewer"])
    org_id: str | None = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(default=["*"])
    expires_at: datetime | None = None


# ── Response models ────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    user_id: str
    email: str
    display_name: str
    roles: list[str]
    org_id: str | None
    is_active: bool
    last_login: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class ApiKeyResponse(BaseModel):
    key_id: str
    name: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreatedResponse(ApiKeyResponse):
    """Returned once at creation — includes the raw key."""
    raw_key: str
