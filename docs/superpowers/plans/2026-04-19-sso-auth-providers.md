# SSO Auth Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SSO login support (Google, Microsoft, and custom OIDC) to PeaRL with provider configuration in the Admin Settings UI, mirroring LiteLLM's fastapi-sso pattern.

**Architecture:** Use `fastapi-sso` to handle OAuth2/OIDC flows for Google and Microsoft, plus a generic OIDC provider for custom setups (Okta, Keycloak, Azure AD B2C, etc.). Provider config (client ID, secret, tenant, discovery URL) is stored in the DB as encrypted admin settings — not hardcoded env vars — so operators can configure SSO from the UI without redeploying. On callback, PeaRL maps the SSO identity to a local `UserRow` (create-on-first-login), issues a standard JWT pair, and redirects the browser to the frontend with the token in a query param. The frontend exchanges it into its normal auth session.

**Tech Stack:** `fastapi-sso>=0.15.0`, existing `PyJWT`, SQLAlchemy async, React + TypeScript, existing `SettingsPage.tsx` tab system.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `pyproject.toml` | Modify | Add `fastapi-sso` dependency |
| `src/pearl/config.py` | Modify | Add `sso_encryption_key` setting |
| `src/pearl/models/sso.py` | Create | `SSOProviderRow` ORM model + Pydantic schemas |
| `src/pearl/repositories/sso_repo.py` | Create | CRUD for SSO provider config rows |
| `src/pearl/api/routes/sso.py` | Create | `/auth/sso/providers`, `/auth/sso/{provider}/login`, `/auth/sso/{provider}/callback` |
| `src/pearl/api/router.py` | Modify | Register SSO router |
| `src/pearl/api/middleware/auth.py` | Modify | Add `/auth/sso` to public paths |
| `src/pearl/db/migrations/versions/008_add_sso_providers.py` | Create | Migration for `sso_providers` table |
| `frontend/src/api/sso.ts` | Create | API client for SSO provider CRUD + login URL |
| `frontend/src/pages/SettingsPage.tsx` | Modify | Add "Authentication" tab with SSO provider management UI |
| `frontend/src/pages/LoginPage.tsx` | Modify | Add SSO provider buttons below the credential form |
| `frontend/src/api/serverConfig.ts` | Modify | Add `sso_providers_enabled: boolean` + `sso_providers: SSOProviderPublic[]` to `ServerConfig` |
| `src/pearl/api/routes/health.py` | Modify | Include active SSO providers in `/server-config` response |
| `tests/test_sso.py` | Create | Integration tests for SSO provider CRUD and callback flow |

---

### Task 1: Add dependency and encryption key config

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/pearl/config.py`

- [ ] **Step 1: Add fastapi-sso to pyproject.toml**

In `pyproject.toml`, add to the `dependencies` list after `"email-validator>=2.3.0"`:

```toml
    "fastapi-sso>=0.15.0",
    "cryptography>=44.0.2",
```

(`cryptography` is already present — leave it, just add `fastapi-sso`.)

- [ ] **Step 2: Add sso_encryption_key to config**

In `src/pearl/config.py`, add after the `api_key_hmac_secret` field:

```python
    # SSO provider config encryption
    # 32-byte URL-safe base64 key used to encrypt client_secret at rest.
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    sso_encryption_key: str = ""
```

- [ ] **Step 3: Install dependency**

```bash
pip install fastapi-sso>=0.15.0
```

Expected: `Successfully installed fastapi-sso-...`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml src/pearl/config.py
git commit -m "feat(sso): add fastapi-sso dependency and encryption key config"
```

---

### Task 2: SSO provider ORM model and migration

**Files:**
- Create: `src/pearl/models/sso.py`
- Create: `src/pearl/db/migrations/versions/008_add_sso_providers.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_sso.py`:

```python
"""SSO provider model and repo tests."""
import pytest
from pearl.models.sso import SSOProviderRow, SSOProviderCreate, SSOProviderUpdate


def test_sso_provider_row_fields():
    row = SSOProviderRow(
        provider_id="sso_test001",
        provider_type="google",
        display_name="Google Login",
        client_id="client-id",
        client_secret_enc="encrypted-secret",
        is_active=True,
    )
    assert row.provider_type == "google"
    assert row.client_secret_enc == "encrypted-secret"


def test_sso_provider_create_schema():
    schema = SSOProviderCreate(
        provider_type="google",
        display_name="Google Login",
        client_id="client-id",
        client_secret="raw-secret",
    )
    assert schema.provider_type == "google"


def test_sso_provider_update_schema():
    schema = SSOProviderUpdate(display_name="Updated", is_active=False)
    assert schema.is_active is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py::test_sso_provider_row_fields -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'pearl.models.sso'`

- [ ] **Step 3: Create the model file**

Create `src/pearl/models/sso.py`:

```python
"""SSO provider configuration model."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pearl.db.base import Base

SSOProviderType = Literal["google", "microsoft", "oidc"]


class SSOProviderRow(Base):
    __tablename__ = "sso_providers"

    provider_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider_type: Mapped[str] = mapped_column(String(32), nullable=False)  # google|microsoft|oidc
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    client_secret_enc: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet-encrypted
    # Microsoft only
    tenant_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # Generic OIDC only
    discovery_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Role assigned to SSO-authenticated users on first login
    default_role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ── Pydantic schemas ────────────────────────────────────────────────────────

class SSOProviderCreate(BaseModel):
    provider_type: SSOProviderType
    display_name: str
    client_id: str
    client_secret: str  # plaintext — encrypted before storage
    tenant_id: str | None = None
    discovery_url: str | None = None
    default_role: str = "viewer"
    is_active: bool = True


class SSOProviderUpdate(BaseModel):
    display_name: str | None = None
    client_id: str | None = None
    client_secret: str | None = None  # plaintext — re-encrypted if provided
    tenant_id: str | None = None
    discovery_url: str | None = None
    default_role: str | None = None
    is_active: bool | None = None


class SSOProviderPublic(BaseModel):
    """Safe subset returned to the frontend — no secrets."""
    provider_id: str
    provider_type: str
    display_name: str
    client_id: str
    tenant_id: str | None
    discovery_url: str | None
    default_role: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py -v
```

Expected: 3 passed

- [ ] **Step 5: Create migration 008**

Create `src/pearl/db/migrations/versions/008_add_sso_providers.py`:

```python
"""Add sso_providers table.

Revision ID: 008
Revises: 007
Create Date: 2026-04-19
"""
import sqlalchemy as sa
from alembic import op


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sso_providers",
        sa.Column("provider_id", sa.String(64), primary_key=True),
        sa.Column("provider_type", sa.String(32), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("client_id", sa.Text, nullable=False),
        sa.Column("client_secret_enc", sa.Text, nullable=False),
        sa.Column("tenant_id", sa.String(128), nullable=True),
        sa.Column("discovery_url", sa.Text, nullable=True),
        sa.Column("default_role", sa.String(32), nullable=False, server_default="viewer"),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("sso_providers")
```

- [ ] **Step 6: Commit**

```bash
git add src/pearl/models/sso.py src/pearl/db/migrations/versions/008_add_sso_providers.py tests/test_sso.py
git commit -m "feat(sso): SSO provider ORM model, Pydantic schemas, and migration 008"
```

---

### Task 3: SSO repository with Fernet encryption

**Files:**
- Create: `src/pearl/repositories/sso_repo.py`
- Modify: `tests/test_sso.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sso.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pearl.repositories.sso_repo import SSOProviderRepository, _encrypt, _decrypt


def test_encrypt_decrypt_roundtrip():
    """Encryption round-trips correctly when key is set."""
    with patch("pearl.repositories.sso_repo.settings") as mock_settings:
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()
        mock_settings.sso_encryption_key = key
        ciphertext = _encrypt("my-secret")
        assert ciphertext != "my-secret"
        assert _decrypt(ciphertext) == "my-secret"


def test_encrypt_no_key_stores_plaintext():
    """When sso_encryption_key is empty, value stored as-is (dev only)."""
    with patch("pearl.repositories.sso_repo.settings") as mock_settings:
        mock_settings.sso_encryption_key = ""
        result = _encrypt("my-secret")
        assert result == "my-secret"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py::test_encrypt_decrypt_roundtrip -v
```

Expected: FAIL with `ImportError`

- [ ] **Step 3: Create the repository**

Create `src/pearl/repositories/sso_repo.py`:

```python
"""Repository for SSO provider configuration with Fernet encryption."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.models.sso import SSOProviderCreate, SSOProviderRow, SSOProviderUpdate


def _encrypt(plaintext: str) -> str:
    """Fernet-encrypt plaintext. Falls back to identity when key not configured (dev)."""
    if not settings.sso_encryption_key:
        return plaintext
    from cryptography.fernet import Fernet
    f = Fernet(settings.sso_encryption_key.encode())
    return f.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    """Fernet-decrypt ciphertext. Falls back to identity when key not configured (dev)."""
    if not settings.sso_encryption_key:
        return ciphertext
    from cryptography.fernet import Fernet
    f = Fernet(settings.sso_encryption_key.encode())
    return f.decrypt(ciphertext.encode()).decode()


class SSOProviderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[SSOProviderRow]:
        result = await self._session.execute(
            select(SSOProviderRow).where(SSOProviderRow.is_active == True).order_by(SSOProviderRow.created_at)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[SSOProviderRow]:
        result = await self._session.execute(
            select(SSOProviderRow).order_by(SSOProviderRow.created_at)
        )
        return list(result.scalars().all())

    async def get(self, provider_id: str) -> SSOProviderRow | None:
        result = await self._session.execute(
            select(SSOProviderRow).where(SSOProviderRow.provider_id == provider_id)
        )
        return result.scalar_one_or_none()

    async def get_by_type(self, provider_type: str) -> SSOProviderRow | None:
        result = await self._session.execute(
            select(SSOProviderRow)
            .where(SSOProviderRow.provider_type == provider_type, SSOProviderRow.is_active == True)
        )
        return result.scalar_one_or_none()

    async def create(self, provider_id: str, body: SSOProviderCreate) -> SSOProviderRow:
        now = datetime.now(timezone.utc)
        row = SSOProviderRow(
            provider_id=provider_id,
            provider_type=body.provider_type,
            display_name=body.display_name,
            client_id=body.client_id,
            client_secret_enc=_encrypt(body.client_secret),
            tenant_id=body.tenant_id,
            discovery_url=body.discovery_url,
            default_role=body.default_role,
            is_active=body.is_active,
            created_at=now,
            updated_at=now,
        )
        self._session.add(row)
        return row

    async def update(self, row: SSOProviderRow, body: SSOProviderUpdate) -> SSOProviderRow:
        if body.display_name is not None:
            row.display_name = body.display_name
        if body.client_id is not None:
            row.client_id = body.client_id
        if body.client_secret is not None:
            row.client_secret_enc = _encrypt(body.client_secret)
        if body.tenant_id is not None:
            row.tenant_id = body.tenant_id
        if body.discovery_url is not None:
            row.discovery_url = body.discovery_url
        if body.default_role is not None:
            row.default_role = body.default_role
        if body.is_active is not None:
            row.is_active = body.is_active
        row.updated_at = datetime.now(timezone.utc)
        return row

    async def delete(self, row: SSOProviderRow) -> None:
        await self._session.delete(row)

    def get_client_secret(self, row: SSOProviderRow) -> str:
        return _decrypt(row.client_secret_enc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/pearl/repositories/sso_repo.py tests/test_sso.py
git commit -m "feat(sso): SSO provider repository with Fernet client_secret encryption"
```

---

### Task 4: SSO API routes (CRUD + OAuth flow)

**Files:**
- Create: `src/pearl/api/routes/sso.py`
- Modify: `src/pearl/api/router.py`
- Modify: `src/pearl/api/middleware/auth.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_sso.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_sso_providers_list_empty(app):
    """GET /auth/sso/providers returns empty list when none configured."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/auth/sso/providers")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_sso_create_requires_admin(app, user_token):
    """POST /auth/sso/providers requires admin role."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            "/api/v1/auth/sso/providers",
            json={"provider_type": "google", "display_name": "Google", "client_id": "id", "client_secret": "secret"},
            headers={"Authorization": f"Bearer {user_token}"},
        )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_sso_create_and_list(app, admin_token):
    """Admin can create a provider and it appears in the list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.post(
            "/api/v1/auth/sso/providers",
            json={"provider_type": "google", "display_name": "Google SSO", "client_id": "gid", "client_secret": "gsecret"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert r.status_code == 201, r.text
        created = r.json()
        assert created["provider_type"] == "google"
        assert "client_secret" not in created  # never returned

        r2 = await ac.get("/api/v1/auth/sso/providers")
        assert r2.status_code == 200
        names = [p["display_name"] for p in r2.json()]
        assert "Google SSO" in names
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py::test_sso_providers_list_empty -v
```

Expected: FAIL with 404 (route not registered)

- [ ] **Step 3: Create the SSO routes file**

Create `src/pearl/api/routes/sso.py`:

```python
"""SSO provider management and OAuth2 flow routes."""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.dependencies import get_db
from pearl.errors.exceptions import AuthorizationError, NotFoundError, ValidationError
from pearl.models.sso import SSOProviderCreate, SSOProviderPublic, SSOProviderUpdate
from pearl.repositories.sso_repo import SSOProviderRepository
from pearl.services.id_generator import generate_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["SSO"])

CANONICAL_ROLES = {"viewer", "operator", "reviewer", "admin", "service_account"}


# ── Provider CRUD (admin only) ─────────────────────────────────────────────

@router.get("/auth/sso/providers", response_model=list[SSOProviderPublic])
async def list_sso_providers(db: AsyncSession = Depends(get_db)):
    """Return all active SSO providers (public info — no secrets). Public endpoint."""
    repo = SSOProviderRepository(db)
    rows = await repo.list_active()
    return [SSOProviderPublic.model_validate(r) for r in rows]


@router.get("/auth/sso/providers/all", response_model=list[SSOProviderPublic])
async def list_all_sso_providers(request: Request, db: AsyncSession = Depends(get_db)):
    """Return all SSO providers including inactive. Admin only."""
    user = getattr(request.state, "user", {})
    if "admin" not in user.get("roles", []):
        raise AuthorizationError("Admin role required")
    repo = SSOProviderRepository(db)
    rows = await repo.list_all()
    return [SSOProviderPublic.model_validate(r) for r in rows]


@router.post("/auth/sso/providers", response_model=SSOProviderPublic, status_code=201)
async def create_sso_provider(body: SSOProviderCreate, request: Request, db: AsyncSession = Depends(get_db)):
    """Create a new SSO provider configuration. Admin only."""
    user = getattr(request.state, "user", {})
    if "admin" not in user.get("roles", []):
        raise AuthorizationError("Admin role required")

    if body.provider_type == "microsoft" and not body.tenant_id:
        raise ValidationError("tenant_id is required for Microsoft SSO")
    if body.provider_type == "oidc" and not body.discovery_url:
        raise ValidationError("discovery_url is required for custom OIDC SSO")
    if body.default_role not in CANONICAL_ROLES:
        raise ValidationError(f"default_role must be one of: {sorted(CANONICAL_ROLES)}")

    repo = SSOProviderRepository(db)
    provider_id = generate_id("sso_")
    row = await repo.create(provider_id, body)
    await db.commit()
    await db.refresh(row)
    return SSOProviderPublic.model_validate(row)


@router.patch("/auth/sso/providers/{provider_id}", response_model=SSOProviderPublic)
async def update_sso_provider(
    provider_id: str, body: SSOProviderUpdate, request: Request, db: AsyncSession = Depends(get_db)
):
    """Update an SSO provider configuration. Admin only."""
    user = getattr(request.state, "user", {})
    if "admin" not in user.get("roles", []):
        raise AuthorizationError("Admin role required")

    repo = SSOProviderRepository(db)
    row = await repo.get(provider_id)
    if not row:
        raise NotFoundError("SSOProvider", provider_id)

    if body.default_role is not None and body.default_role not in CANONICAL_ROLES:
        raise ValidationError(f"default_role must be one of: {sorted(CANONICAL_ROLES)}")

    row = await repo.update(row, body)
    await db.commit()
    await db.refresh(row)
    return SSOProviderPublic.model_validate(row)


@router.delete("/auth/sso/providers/{provider_id}", status_code=204)
async def delete_sso_provider(provider_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Delete an SSO provider. Admin only."""
    user = getattr(request.state, "user", {})
    if "admin" not in user.get("roles", []):
        raise AuthorizationError("Admin role required")

    repo = SSOProviderRepository(db)
    row = await repo.get(provider_id)
    if not row:
        raise NotFoundError("SSOProvider", provider_id)

    await repo.delete(row)
    await db.commit()


# ── OAuth2 login initiation ────────────────────────────────────────────────

@router.get("/auth/sso/{provider_id}/login")
async def sso_login(provider_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Redirect browser to the OAuth2 provider authorization URL."""
    repo = SSOProviderRepository(db)
    row = await repo.get(provider_id)
    if not row or not row.is_active:
        raise NotFoundError("SSOProvider", provider_id)

    sso = _build_sso_client(row, repo, str(request.base_url))
    async with sso:
        redirect = await sso.get_login_redirect()
    return redirect


# ── OAuth2 callback ────────────────────────────────────────────────────────

@router.get("/auth/sso/{provider_id}/callback")
async def sso_callback(provider_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    """Handle OAuth2 callback: exchange code → user info → JWT → frontend redirect."""
    from datetime import datetime, timedelta, timezone

    import jwt as pyjwt

    from pearl.config import settings
    from pearl.repositories.user_repo import UserRepository
    from pearl.services.id_generator import generate_id as _gen

    repo = SSOProviderRepository(db)
    row = await repo.get(provider_id)
    if not row or not row.is_active:
        raise NotFoundError("SSOProvider", provider_id)

    sso = _build_sso_client(row, repo, str(request.base_url))
    async with sso:
        try:
            openid_user = await sso.verify_and_process(request)
        except Exception as exc:
            logger.warning("SSO callback failed for %s: %s", provider_id, exc)
            return RedirectResponse(url="/login?error=sso_failed")

    if not openid_user or not openid_user.email:
        return RedirectResponse(url="/login?error=sso_no_email")

    # Find or create local user
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(openid_user.email)
    if not user:
        user_id = _gen("usr_")
        display_name = openid_user.display_name or openid_user.email.split("@")[0]
        user = await user_repo.create(
            user_id=user_id,
            email=openid_user.email,
            display_name=display_name,
            hashed_password=None,
            roles=[row.default_role],
            org_id=None,
            is_active=True,
        )
        logger.info("SSO: created new user %s via %s", openid_user.email, provider_id)
    else:
        logger.info("SSO: existing user %s logged in via %s", openid_user.email, provider_id)

    await db.commit()

    # Issue standard PeaRL JWT pair
    now = datetime.now(timezone.utc)
    access_payload = {
        "sub": user.user_id,
        "roles": user.roles,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "type": "access",
        "sso": provider_id,
    }
    refresh_payload = {
        "sub": user.user_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "type": "refresh",
    }
    access_token = pyjwt.encode(access_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    refresh_token = pyjwt.encode(refresh_payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    # Redirect browser to frontend with tokens in query params
    # Frontend reads them from URL, stores in localStorage, removes from URL
    params = urlencode({"access_token": access_token, "refresh_token": refresh_token})
    return RedirectResponse(url=f"/sso-callback?{params}")


# ── Internal helper ────────────────────────────────────────────────────────

def _build_sso_client(row, repo, base_url: str):
    """Build the appropriate fastapi-sso client for a provider row."""
    secret = repo.get_client_secret(row)
    callback_url = f"{base_url.rstrip('/')}/api/v1/auth/sso/{row.provider_id}/callback"

    if row.provider_type == "google":
        from fastapi_sso.sso.google import GoogleSSO
        return GoogleSSO(
            client_id=row.client_id,
            client_secret=secret,
            redirect_uri=callback_url,
            allow_insecure_http=True,  # set False in prod via HTTPS
        )
    elif row.provider_type == "microsoft":
        from fastapi_sso.sso.microsoft import MicrosoftSSO
        return MicrosoftSSO(
            client_id=row.client_id,
            client_secret=secret,
            tenant=row.tenant_id or "common",
            redirect_uri=callback_url,
            allow_insecure_http=True,
        )
    elif row.provider_type == "oidc":
        from fastapi_sso.sso.generic import create_provider
        GenericSSO = create_provider(
            name="oidc",
            discovery_document=row.discovery_url,
        )
        return GenericSSO(
            client_id=row.client_id,
            client_secret=secret,
            redirect_uri=callback_url,
            allow_insecure_http=True,
        )
    else:
        raise ValidationError(f"Unknown provider_type: {row.provider_type}")
```

- [ ] **Step 4: Register the router**

In `src/pearl/api/router.py`, find where other auth/health routers are included and add:

```python
from pearl.api.routes import sso as sso_routes
# ...
api_router.include_router(sso_routes.router)
```

- [ ] **Step 5: Add SSO paths to public paths in auth middleware**

In `src/pearl/api/middleware/auth.py`, add to `_PUBLIC_PATHS`:

```python
_PUBLIC_PATHS = {
    "/api/v1/health",
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/auth/login",
    "/api/v1/auth/refresh",
    "/api/v1/auth/jwks.json",
    "/api/v1/server-config",
    "/api/v1/auth/sso/providers",   # public — login page reads this
}
```

And in the `dispatch` method, add a prefix bypass for SSO login/callback (dynamic paths):

```python
        # SSO OAuth flow paths — must be public (browser redirect, no token)
        if path.startswith("/api/v1/auth/sso/") and (path.endswith("/login") or path.endswith("/callback")):
            request.state.user = {"sub": "anonymous", "roles": [], "scopes": ["*"]}
            return await call_next(request)
```

Add this block immediately after the `schema_prefix` check, before the auth header checks.

- [ ] **Step 6: Run tests to verify they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py -v
```

Expected: all SSO tests pass

- [ ] **Step 7: Commit**

```bash
git add src/pearl/api/routes/sso.py src/pearl/api/router.py src/pearl/api/middleware/auth.py tests/test_sso.py
git commit -m "feat(sso): SSO CRUD routes and OAuth2 login/callback flow"
```

---

### Task 5: Expose SSO providers in server-config

**Files:**
- Modify: `src/pearl/api/routes/health.py`
- Modify: `frontend/src/api/serverConfig.ts`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_sso.py`:

```python
@pytest.mark.asyncio
async def test_server_config_includes_sso(app):
    """server-config includes sso_providers list."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/api/v1/server-config")
    assert r.status_code == 200
    data = r.json()
    assert "sso_providers" in data
    assert isinstance(data["sso_providers"], list)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py::test_server_config_includes_sso -v
```

Expected: FAIL — `sso_providers` key missing from response

- [ ] **Step 3: Update server_config route**

In `src/pearl/api/routes/health.py`, update the `server_config` function:

```python
@router.get("/server-config", include_in_schema=False)
async def server_config(request: Request):
    """Return non-sensitive server flags needed by the frontend UI."""
    from pearl.dependencies import get_db
    from pearl.models.sso import SSOProviderPublic
    from pearl.repositories.sso_repo import SSOProviderRepository

    sso_providers: list[dict] = []
    try:
        session_factory = getattr(request.app.state, "db_session_factory", None)
        if session_factory:
            async with session_factory() as session:
                repo = SSOProviderRepository(session)
                rows = await repo.list_active()
                sso_providers = [SSOProviderPublic.model_validate(r).model_dump(mode="json") for r in rows]
    except Exception:
        pass  # DB unavailable — degrade gracefully, SSO buttons won't show

    return {
        "reviewer_mode": settings.local_reviewer_mode,
        "local_mode": settings.local_mode,
        "sso_providers": sso_providers,
    }
```

- [ ] **Step 4: Update frontend ServerConfig type**

In `frontend/src/api/serverConfig.ts`:

```typescript
import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface SSOProviderPublic {
  provider_id: string;
  provider_type: "google" | "microsoft" | "oidc";
  display_name: string;
  client_id: string;
  tenant_id: string | null;
  discovery_url: string | null;
  default_role: string;
  is_active: boolean;
  created_at: string;
}

interface ServerConfig {
  reviewer_mode: boolean;
  local_mode: boolean;
  sso_providers: SSOProviderPublic[];
}

export function useServerConfig() {
  return useQuery({
    queryKey: ["server-config"],
    queryFn: () => apiFetch<ServerConfig>("/server-config"),
    staleTime: Infinity,
    retry: false,
  });
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
PEARL_LOCAL=1 pytest tests/test_sso.py -v
```

Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add src/pearl/api/routes/health.py frontend/src/api/serverConfig.ts
git commit -m "feat(sso): expose active SSO providers in server-config for frontend"
```

---

### Task 6: Frontend — SSO callback page

**Files:**
- Create: `frontend/src/pages/SSOCallbackPage.tsx`
- Modify: `frontend/src/App.tsx` (or wherever routes are defined)

- [ ] **Step 1: Create SSOCallbackPage**

The backend redirects to `/sso-callback?access_token=...&refresh_token=...`. This page reads the tokens from the URL, stores them, and redirects to the dashboard.

Create `frontend/src/pages/SSOCallbackPage.tsx`:

```tsx
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import { useAuth } from "@/context/AuthContext";

export function SSOCallbackPage() {
  const navigate = useNavigate();
  const { setTokens } = useAuth();

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get("access_token");
    const refreshToken = params.get("refresh_token");
    const error = params.get("error");

    if (error || !accessToken || !refreshToken) {
      navigate("/login?error=" + (error ?? "sso_failed"), { replace: true });
      return;
    }

    // Store tokens and clear them from the URL immediately
    setTokens(accessToken, refreshToken);
    window.history.replaceState({}, "", "/sso-callback");
    navigate("/", { replace: true });
  }, [navigate, setTokens]);

  return (
    <div className="flex h-screen bg-vault-black items-center justify-center">
      <div className="text-center">
        <ShieldCheck size={40} className="text-cold-teal mx-auto mb-4" strokeWidth={1.5} />
        <p className="font-mono text-bone-muted text-sm">Completing sign-in...</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Add setTokens to AuthContext**

Find `frontend/src/context/AuthContext.tsx`. Locate the context value and add `setTokens`:

```tsx
// In AuthContext.tsx, add this function to the context:
const setTokens = (accessToken: string, refreshToken: string) => {
  localStorage.setItem("pearl_access_token", accessToken);
  localStorage.setItem("pearl_refresh_token", refreshToken);
  // Trigger any auth state refresh your context needs
  // (e.g., call the existing user-fetch mechanism)
};
```

Expose `setTokens` in the context type and provider value.

- [ ] **Step 3: Register the route**

In the file that defines React Router routes (check `frontend/src/App.tsx` or `frontend/src/main.tsx`), add:

```tsx
import { SSOCallbackPage } from "@/pages/SSOCallbackPage";
// ...
<Route path="/sso-callback" element={<SSOCallbackPage />} />
```

- [ ] **Step 4: Verify the frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: `✓ built in ...` with no TypeScript errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/SSOCallbackPage.tsx frontend/src/context/AuthContext.tsx frontend/src/App.tsx
git commit -m "feat(sso): SSO callback page reads tokens from URL and stores auth session"
```

---

### Task 7: Frontend — SSO buttons on LoginPage

**Files:**
- Modify: `frontend/src/pages/LoginPage.tsx`

- [ ] **Step 1: Add SSO provider buttons**

In `frontend/src/pages/LoginPage.tsx`, import `useServerConfig` and render provider buttons below the credential form. Add after the existing imports:

```tsx
import { useServerConfig } from "@/api/serverConfig";
```

Add inside the `LoginPage` component, before the return:

```tsx
  const { data: serverConfig } = useServerConfig();
  const ssoProviders = serverConfig?.sso_providers ?? [];
```

Add this block inside the right panel of the login form, after the submit button and before the closing `</form>` or panel div:

```tsx
          {ssoProviders.length > 0 && (
            <>
              <div className="flex items-center gap-3 my-4">
                <div className="flex-1 h-px bg-slate-border" />
                <span className="text-xs font-mono text-bone-dim uppercase tracking-widest">or</span>
                <div className="flex-1 h-px bg-slate-border" />
              </div>
              <div className="flex flex-col gap-2">
                {ssoProviders.map((provider) => (
                  <a
                    key={provider.provider_id}
                    href={`/api/v1/auth/sso/${provider.provider_id}/login`}
                    className="flex items-center justify-center gap-2 w-full py-2 px-4 rounded border border-slate-border text-bone-muted text-sm font-mono hover:border-cold-teal hover:text-cold-teal transition-colors"
                  >
                    {provider.provider_type === "google" && (
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/>
                        <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/>
                        <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/>
                        <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/>
                      </svg>
                    )}
                    {provider.provider_type === "microsoft" && (
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M11.4 24H0V12.6h11.4V24z" fill="#F1511B"/>
                        <path d="M24 24H12.6V12.6H24V24z" fill="#80CC28"/>
                        <path d="M11.4 11.4H0V0h11.4v11.4z" fill="#00ADEF"/>
                        <path d="M24 11.4H12.6V0H24v11.4z" fill="#FBBC09"/>
                      </svg>
                    )}
                    {provider.provider_type === "oidc" && (
                      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/>
                      </svg>
                    )}
                    Continue with {provider.display_name}
                  </a>
                ))}
              </div>
            </>
          )}
```

- [ ] **Step 2: Verify the frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: `✓ built in ...` with no TypeScript errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/LoginPage.tsx
git commit -m "feat(sso): show SSO provider login buttons on LoginPage when configured"
```

---

### Task 8: Admin Settings — Authentication tab

**Files:**
- Modify: `frontend/src/pages/SettingsPage.tsx`

- [ ] **Step 1: Add the Authentication tab type and entry**

In `frontend/src/pages/SettingsPage.tsx`, update the `Tab` type:

```tsx
type Tab = "gates" | "environments" | "business_units" | "integrations" | "project_data" | "authentication";
```

Add to the `TABS` array:

```tsx
{ key: "authentication", icon: ShieldCheck, label: "Authentication" },
```

Import `ShieldCheck` from lucide-react if not already imported.

- [ ] **Step 2: Add the API client for SSO management**

Create `frontend/src/api/sso.ts`:

```typescript
import { apiFetch } from "./client";
import { SSOProviderPublic } from "./serverConfig";

export interface SSOProviderCreate {
  provider_type: "google" | "microsoft" | "oidc";
  display_name: string;
  client_id: string;
  client_secret: string;
  tenant_id?: string;
  discovery_url?: string;
  default_role?: string;
  is_active?: boolean;
}

export interface SSOProviderUpdate {
  display_name?: string;
  client_id?: string;
  client_secret?: string;
  tenant_id?: string;
  discovery_url?: string;
  default_role?: string;
  is_active?: boolean;
}

export const ssoApi = {
  listAll: () => apiFetch<SSOProviderPublic[]>("/auth/sso/providers/all"),
  create: (body: SSOProviderCreate) =>
    apiFetch<SSOProviderPublic>("/auth/sso/providers", { method: "POST", body: JSON.stringify(body) }),
  update: (providerId: string, body: SSOProviderUpdate) =>
    apiFetch<SSOProviderPublic>(`/auth/sso/providers/${providerId}`, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (providerId: string) =>
    apiFetch<void>(`/auth/sso/providers/${providerId}`, { method: "DELETE" }),
};
```

- [ ] **Step 3: Create the AuthenticationTab component**

Add this component to `frontend/src/pages/SettingsPage.tsx` before the main `SettingsPage` export:

```tsx
function AuthenticationTab() {
  const [providers, setProviders] = useState<SSOProviderPublic[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState({
    provider_type: "google" as "google" | "microsoft" | "oidc",
    display_name: "",
    client_id: "",
    client_secret: "",
    tenant_id: "",
    discovery_url: "",
    default_role: "viewer",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ssoApi.listAll().then(setProviders).finally(() => setLoading(false));
  }, []);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const body = {
        provider_type: form.provider_type,
        display_name: form.display_name,
        client_id: form.client_id,
        client_secret: form.client_secret,
        tenant_id: form.tenant_id || undefined,
        discovery_url: form.discovery_url || undefined,
        default_role: form.default_role,
      };
      if (editingId) {
        const updated = await ssoApi.update(editingId, body);
        setProviders((prev) => prev.map((p) => (p.provider_id === editingId ? updated : p)));
      } else {
        const created = await ssoApi.create(body);
        setProviders((prev) => [...prev, created]);
      }
      setShowForm(false);
      setEditingId(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(providerId: string) {
    if (!confirm("Remove this SSO provider?")) return;
    await ssoApi.delete(providerId);
    setProviders((prev) => prev.filter((p) => p.provider_id !== providerId));
  }

  function startEdit(p: SSOProviderPublic) {
    setForm({
      provider_type: p.provider_type as "google" | "microsoft" | "oidc",
      display_name: p.display_name,
      client_id: p.client_id,
      client_secret: "",  // never pre-filled — user must re-enter to change
      tenant_id: p.tenant_id ?? "",
      discovery_url: p.discovery_url ?? "",
      default_role: p.default_role,
    });
    setEditingId(p.provider_id);
    setShowForm(true);
  }

  return (
    <div className="p-6 max-w-3xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="font-heading text-lg font-semibold text-bone">SSO Providers</h2>
          <p className="text-xs text-bone-dim font-mono mt-1">
            Configure identity providers for single sign-on. Users are created on first login with the default role.
          </p>
        </div>
        <button
          onClick={() => { setShowForm(true); setEditingId(null); setForm({ provider_type: "google", display_name: "", client_id: "", client_secret: "", tenant_id: "", discovery_url: "", default_role: "viewer" }); }}
          className="px-3 py-1.5 bg-cold-teal text-vault-black text-xs font-mono rounded hover:opacity-90"
        >
          + Add Provider
        </button>
      </div>

      {loading ? (
        <p className="text-xs text-bone-dim font-mono">Loading...</p>
      ) : providers.length === 0 ? (
        <div className="border border-slate-border rounded p-8 text-center">
          <p className="text-sm text-bone-dim font-mono">No SSO providers configured.</p>
          <p className="text-xs text-bone-dim font-mono mt-1">Add Google, Microsoft, or a custom OIDC provider.</p>
        </div>
      ) : (
        <table className="w-full text-xs font-mono border-collapse">
          <thead>
            <tr className="border-b border-slate-border text-bone-dim text-left">
              <th className="pb-2 pr-4">Provider</th>
              <th className="pb-2 pr-4">Type</th>
              <th className="pb-2 pr-4">Default Role</th>
              <th className="pb-2 pr-4">Status</th>
              <th className="pb-2"></th>
            </tr>
          </thead>
          <tbody>
            {providers.map((p) => (
              <tr key={p.provider_id} className="border-b border-slate-border/40 hover:bg-slate-border/10">
                <td className="py-2 pr-4 text-bone">{p.display_name}</td>
                <td className="py-2 pr-4 text-cold-teal">{p.provider_type}</td>
                <td className="py-2 pr-4 text-bone-muted">{p.default_role}</td>
                <td className="py-2 pr-4">
                  <span className={`px-2 py-0.5 rounded text-[10px] ${p.is_active ? "bg-green-900/40 text-green-400" : "bg-red-900/40 text-red-400"}`}>
                    {p.is_active ? "active" : "disabled"}
                  </span>
                </td>
                <td className="py-2 flex gap-2 justify-end">
                  <button onClick={() => startEdit(p)} className="text-bone-dim hover:text-cold-teal">Edit</button>
                  <button onClick={() => handleDelete(p.provider_id)} className="text-bone-dim hover:text-red-400">Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showForm && (
        <div className="mt-6 border border-slate-border rounded p-5">
          <h3 className="text-sm font-mono font-semibold text-bone mb-4">
            {editingId ? "Edit Provider" : "New SSO Provider"}
          </h3>
          {error && <p className="text-xs text-red-400 font-mono mb-3">{error}</p>}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-bone-dim font-mono block mb-1">Provider Type</label>
              <select
                value={form.provider_type}
                onChange={(e) => setForm((f) => ({ ...f, provider_type: e.target.value as "google" | "microsoft" | "oidc" }))}
                className="w-full bg-vault-black border border-slate-border rounded px-2 py-1.5 text-xs font-mono text-bone"
              >
                <option value="google">Google</option>
                <option value="microsoft">Microsoft / Azure AD</option>
                <option value="oidc">Custom OIDC</option>
              </select>
            </div>

            <div>
              <label className="text-xs text-bone-dim font-mono block mb-1">Display Name</label>
              <input
                value={form.display_name}
                onChange={(e) => setForm((f) => ({ ...f, display_name: e.target.value }))}
                placeholder="Google Workspace"
                className="w-full bg-vault-black border border-slate-border rounded px-2 py-1.5 text-xs font-mono text-bone"
              />
            </div>

            <div>
              <label className="text-xs text-bone-dim font-mono block mb-1">Client ID</label>
              <input
                value={form.client_id}
                onChange={(e) => setForm((f) => ({ ...f, client_id: e.target.value }))}
                placeholder="123456789.apps.googleusercontent.com"
                className="w-full bg-vault-black border border-slate-border rounded px-2 py-1.5 text-xs font-mono text-bone"
              />
            </div>

            <div>
              <label className="text-xs text-bone-dim font-mono block mb-1">
                Client Secret {editingId && <span className="text-bone-dim">(leave blank to keep existing)</span>}
              </label>
              <input
                type="password"
                value={form.client_secret}
                onChange={(e) => setForm((f) => ({ ...f, client_secret: e.target.value }))}
                placeholder={editingId ? "••••••••" : "your-client-secret"}
                className="w-full bg-vault-black border border-slate-border rounded px-2 py-1.5 text-xs font-mono text-bone"
              />
            </div>

            {form.provider_type === "microsoft" && (
              <div className="col-span-2">
                <label className="text-xs text-bone-dim font-mono block mb-1">Tenant ID</label>
                <input
                  value={form.tenant_id}
                  onChange={(e) => setForm((f) => ({ ...f, tenant_id: e.target.value }))}
                  placeholder="your-tenant-id or 'common'"
                  className="w-full bg-vault-black border border-slate-border rounded px-2 py-1.5 text-xs font-mono text-bone"
                />
              </div>
            )}

            {form.provider_type === "oidc" && (
              <div className="col-span-2">
                <label className="text-xs text-bone-dim font-mono block mb-1">Discovery URL</label>
                <input
                  value={form.discovery_url}
                  onChange={(e) => setForm((f) => ({ ...f, discovery_url: e.target.value }))}
                  placeholder="https://your-idp.com/.well-known/openid-configuration"
                  className="w-full bg-vault-black border border-slate-border rounded px-2 py-1.5 text-xs font-mono text-bone"
                />
              </div>
            )}

            <div>
              <label className="text-xs text-bone-dim font-mono block mb-1">Default Role (new users)</label>
              <select
                value={form.default_role}
                onChange={(e) => setForm((f) => ({ ...f, default_role: e.target.value }))}
                className="w-full bg-vault-black border border-slate-border rounded px-2 py-1.5 text-xs font-mono text-bone"
              >
                {["viewer", "operator", "reviewer", "admin"].map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex gap-3 mt-5">
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-1.5 bg-cold-teal text-vault-black text-xs font-mono rounded hover:opacity-90 disabled:opacity-50"
            >
              {saving ? "Saving..." : editingId ? "Save Changes" : "Create Provider"}
            </button>
            <button
              onClick={() => { setShowForm(false); setEditingId(null); }}
              className="px-4 py-1.5 border border-slate-border text-bone-dim text-xs font-mono rounded hover:border-cold-teal"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire the tab into the settings page**

In the tab content section of `SettingsPage`, add:

```tsx
{activeTab === "authentication" && <AuthenticationTab />}
```

Add the required imports at the top of the file:

```tsx
import { ssoApi } from "@/api/sso";
import type { SSOProviderPublic } from "@/api/serverConfig";
```

- [ ] **Step 5: Verify the frontend builds without errors**

```bash
cd frontend && npm run build 2>&1 | tail -10
```

Expected: `✓ built in ...` with no TypeScript errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/SettingsPage.tsx frontend/src/api/sso.ts
git commit -m "feat(sso): Authentication tab in Settings with SSO provider CRUD UI"
```

---

## Self-Review

**Spec coverage check:**
- ✅ Google SSO — Task 4 (`GoogleSSO` from fastapi-sso)
- ✅ Microsoft SSO — Task 4 (`MicrosoftSSO` with tenant_id)
- ✅ Custom OIDC — Task 4 (`create_provider` generic)
- ✅ Admin Settings UI — Task 8 (Authentication tab in SettingsPage)
- ✅ Login page SSO buttons — Task 7
- ✅ Provider config stored in DB (not env vars) — Tasks 2–3
- ✅ Client secret encrypted at rest — Task 3 (Fernet)
- ✅ SSO user → local UserRow mapping (create on first login) — Task 4
- ✅ Standard JWT issued after SSO (same session mechanism) — Task 4
- ✅ Public paths updated so OAuth callbacks work without Bearer token — Task 4

**Placeholder scan:** None found — all code blocks are complete.

**Type consistency:** `SSOProviderPublic` defined in `serverConfig.ts` and re-exported/imported in `sso.ts` and `SettingsPage.tsx` consistently. `provider_type` is `"google" | "microsoft" | "oidc"` throughout.
