"""Authentication and user management routes."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.config import settings
from pearl.dependencies import get_db, get_trace_id
from pearl.errors.exceptions import AuthenticationError, AuthorizationError, ConflictError, NotFoundError
from pearl.models.user import (
    ApiKeyCreate,
    ApiKeyCreatedResponse,
    ApiKeyResponse,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from pearl.repositories.compiled_package_repo import CompiledPackageRepository
from pearl.repositories.fairness_repo import AuditEventRepository
from pearl.repositories.user_repo import ApiKeyRepository, UserRepository
from pearl.services.id_generator import generate_id

router = APIRouter(tags=["Auth"])


# ── JWT helpers ────────────────────────────────────────────────────────────────

def _make_tokens(user_id: str, roles: list[str]) -> tuple[str, str]:
    """Return (access_token, refresh_token)."""
    import jwt as pyjwt

    now = datetime.now(timezone.utc)
    access_payload = {
        "sub": user_id,
        "roles": roles,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
        "type": "access",
    }
    refresh_payload = {
        "sub": user_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
        "type": "refresh",
    }

    key = settings.jwt_secret
    algo = settings.jwt_algorithm
    access_token = pyjwt.encode(access_payload, key, algorithm=algo)
    refresh_token = pyjwt.encode(refresh_payload, key, algorithm=algo)
    return access_token, refresh_token


def _hash_password(password: str) -> str:
    import hashlib
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{h.hex()}"


def _verify_password(password: str, hashed: str) -> bool:
    import hashlib
    parts = hashed.split(":", 1)
    if len(parts) != 2:
        return False
    salt_hex, stored = parts
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return secrets.compare_digest(h.hex(), stored)


def _hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode()).hexdigest()


# ── Auth endpoints ─────────────────────────────────────────────────────────────

@router.post("/auth/login", response_model=TokenResponse)
async def login(body: UserLogin, db: AsyncSession = Depends(get_db)):
    repo = UserRepository(db)
    user = await repo.get_by_email(body.email)
    if not user or not user.hashed_password or not user.is_active:
        raise AuthenticationError("Invalid email or password")
    if not _verify_password(body.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password")

    await repo.update_last_login(user)
    await db.commit()

    access_token, refresh_token = _make_tokens(user.user_id, user.roles)
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    token = body.get("refresh_token", "")

    import jwt as pyjwt
    try:
        header = pyjwt.get_unverified_header(token)
        if "crit" in header:
            raise AuthenticationError("Token contains unsupported critical header extensions")
        payload = pyjwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except pyjwt.exceptions.PyJWTError as exc:
        raise AuthenticationError(f"Invalid refresh token: {exc}") from exc

    if payload.get("type") != "refresh":
        raise AuthenticationError("Not a refresh token")

    # Check blocklist in Redis
    redis = getattr(request.app.state, "redis", None)
    if redis:
        blocked = await redis.get(f"pearl:token:blocked:{token[:32]}")
        if blocked:
            raise AuthenticationError("Token has been revoked")

    repo = UserRepository(db)
    user = await repo.get(payload["sub"])
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive")

    access_token, new_refresh = _make_tokens(user.user_id, user.roles)
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/auth/logout", status_code=204)
async def logout(request: Request):
    body = await request.json()
    token = body.get("refresh_token", "")
    redis = getattr(request.app.state, "redis", None)
    if redis and token:
        await redis.setex(
            f"pearl:token:blocked:{token[:32]}",
            settings.jwt_refresh_token_expire_days * 86400,
            "1",
        )


@router.post("/auth/project-token")
async def issue_project_token(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Issue a short-lived project-scoped token with ACoP claims (§8.5).

    The caller must hold a valid access token. The returned token adds:
    - ``acop_contract_id`` — latest compiled package ID
    - ``acop_environment`` — project's current environment
    - ``acop_cih`` — contract integrity hash (``sha256-{hex}``)
    - ``acop_permitted_tools`` — allowed tool classes from the compiled contract
    """
    import jwt as pyjwt

    current_user = getattr(request.state, "user", {})
    user_id = current_user.get("sub")
    if not user_id or user_id in ("anonymous", "dev-user"):
        raise AuthenticationError("Authentication required")

    body = await request.json()
    project_id = body.get("project_id")
    if not project_id:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError("project_id is required")

    pkg_repo = CompiledPackageRepository(db)
    pkg_row = await pkg_repo.get_latest_by_project(project_id)
    if not pkg_row:
        raise NotFoundError("Compiled package", project_id)

    pkg_data = pkg_row.package_data
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "roles": current_user.get("roles", []),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + timedelta(minutes=15),  # Short-lived — scope to one project session
        "type": "access",
        # ACoP §8.5 custom claims
        "acop_contract_id": pkg_row.package_id,
        "acop_environment": pkg_data.get("project_identity", {}).get("environment", ""),
        "acop_cih": pkg_row.integrity_hash or "",
        "acop_permitted_tools": (
            pkg_data.get("tool_and_model_constraints", {}).get("allowed_tool_classes", [])
        ),
        "acop_project_id": project_id,
    }
    token = pyjwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 15 * 60,
        "acop_contract_id": pkg_row.package_id,
        "acop_environment": payload["acop_environment"],
        "acop_cih": payload["acop_cih"],
    }


@router.get("/auth/jwks.json")
async def jwks():
    """Expose public key as JWKS (RS256 only)."""
    if settings.jwt_algorithm != "RS256" or not settings.jwt_public_key_path:
        return {"keys": []}

    import jwt as pyjwt
    from pathlib import Path
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pub_pem = Path(settings.jwt_public_key_path).read_bytes()
    public_key = load_pem_public_key(pub_pem)
    jwk_dict = pyjwt.algorithms.RSAAlgorithm.to_jwk(public_key, as_dict=True)
    return {"keys": [jwk_dict]}


# ── User management ────────────────────────────────────────────────────────────

@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Require admin role
    current_user = getattr(request.state, "user", {})
    if "admin" not in current_user.get("roles", []):
        raise AuthorizationError("Admin role required to create users")

    repo = UserRepository(db)
    existing = await repo.get_by_email(body.email)
    if existing:
        raise ConflictError(f"User with email '{body.email}' already exists")

    from pearl.dependencies import CANONICAL_ROLES
    invalid_roles = [r for r in (body.roles or []) if r not in CANONICAL_ROLES]
    if invalid_roles:
        from pearl.errors.exceptions import ValidationError
        raise ValidationError(f"Invalid roles: {invalid_roles}. Must be one of: {list(CANONICAL_ROLES)}")

    user_id = generate_id("usr_")
    hashed = _hash_password(body.password)
    user = await repo.create(
        user_id=user_id,
        email=body.email,
        display_name=body.display_name,
        hashed_password=hashed,
        roles=body.roles,
        org_id=body.org_id,
        is_active=True,
    )
    await AuditEventRepository(db).append(
        event_id=generate_id("evt_"),
        resource_id=user_id,
        action_type="user.created",
        actor=current_user.get("sub"),
        details={"email": body.email, "roles": body.roles},
    )
    await db.commit()
    return UserResponse.model_validate(user)


@router.get("/users/me", response_model=UserResponse)
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    current = getattr(request.state, "user", {})
    user_id = current.get("sub")
    if not user_id or user_id in ("anonymous", "dev-user"):
        raise AuthenticationError("Authentication required")

    repo = UserRepository(db)
    user = await repo.get(user_id)
    if not user:
        raise NotFoundError("User", user_id)
    return UserResponse.model_validate(user)


# ── API key management ─────────────────────────────────────────────────────────

@router.post("/users/me/api-keys", response_model=ApiKeyCreatedResponse, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current = getattr(request.state, "user", {})
    user_id = current.get("sub")
    if not user_id or user_id in ("anonymous", "dev-user"):
        raise AuthenticationError("Authentication required")

    raw_key = f"pk_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)

    repo = ApiKeyRepository(db)
    key_id = generate_id("key_")
    key = await repo.create(
        key_id=key_id,
        user_id=user_id,
        key_hash=key_hash,
        name=body.name,
        scopes=body.scopes,
        expires_at=body.expires_at,
        is_active=True,
    )
    await AuditEventRepository(db).append(
        event_id=generate_id("evt_"),
        resource_id=key_id,
        action_type="api_key.created",
        actor=user_id,
        details={"name": body.name, "scopes": body.scopes},
    )
    await db.commit()

    response = ApiKeyCreatedResponse.model_validate(key)
    response.raw_key = raw_key
    return response


@router.get("/users/me/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(request: Request, db: AsyncSession = Depends(get_db)):
    current = getattr(request.state, "user", {})
    user_id = current.get("sub")
    if not user_id or user_id in ("anonymous", "dev-user"):
        raise AuthenticationError("Authentication required")

    repo = ApiKeyRepository(db)
    keys = await repo.list_for_user(user_id)
    return [ApiKeyResponse.model_validate(k) for k in keys]


@router.delete("/users/me/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    key_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current = getattr(request.state, "user", {})
    user_id = current.get("sub")
    if not user_id or user_id in ("anonymous", "dev-user"):
        raise AuthenticationError("Authentication required")

    repo = ApiKeyRepository(db)
    key = await repo.get_by_id("key_id", key_id)
    if not key or key.user_id != user_id:
        raise NotFoundError("ApiKey", key_id)
    await repo.revoke(key)
    await db.commit()
