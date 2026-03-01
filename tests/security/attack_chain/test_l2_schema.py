"""L2 — OpenAPI Schema Discovery

Attack chain level 2: an autonomous agent calls /openapi.json, /docs,
or /redoc to discover all governance endpoints and their schemas before
targeting specific routes.

Hard control tested:
  - /openapi.json returns 404 when expose_openapi=False (production mode)
  - /docs returns 404 in production mode
  - /redoc returns 404 in production mode

Note on local vs production mode:
  The schema IS intentionally exposed in PEARL_LOCAL=1 (local dev) mode —
  developers need it. This control is production-only, enforced via
  settings.effective_expose_openapi = False when PEARL_LOCAL is unset.
  These tests use prod_client (expose_openapi=False) to verify the control.

Positive test:
  - The API itself still works normally (routes are not disabled)

Reference: pearl_autonomous_attack_research.md L2
Control: openapi_url=None / docs_url=None / redoc_url=None in src/pearl/main.py
         when settings.effective_expose_openapi is False
"""

import pytest


# ---------------------------------------------------------------------------
# L2 hard control: schema discovery endpoints disabled in prod mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l2_openapi_json_not_accessible(prod_client):
    """
    L2 control: /openapi.json returns 404 in production mode.

    Attack: agent fetches the schema to learn all governance endpoint paths
    and request bodies before constructing targeted requests.
    Expected: 404 — schema endpoint is not registered.
    Control: openapi_url=None in create_app() when expose_openapi=False
    """
    response = await prod_client.get("/openapi.json")
    assert response.status_code == 404, (
        f"Expected 404 for /openapi.json (schema discovery disabled), "
        f"got {response.status_code}. "
        f"Ensure openapi_url=None in create_app() when expose_openapi=False."
    )


@pytest.mark.asyncio
async def test_l2_docs_ui_not_accessible(prod_client):
    """
    L2 control: /docs (Swagger UI) returns 404 in production mode.

    Expected: 404 — interactive docs are not registered.
    Control: docs_url=None in create_app() when expose_openapi=False
    """
    response = await prod_client.get("/docs")
    assert response.status_code == 404, (
        f"Expected 404 for /docs (Swagger UI disabled), got {response.status_code}."
    )


@pytest.mark.asyncio
async def test_l2_redoc_not_accessible(prod_client):
    """
    L2 control: /redoc returns 404 in production mode.

    Expected: 404 — ReDoc UI is not registered.
    Control: redoc_url=None in create_app() when expose_openapi=False
    """
    response = await prod_client.get("/redoc")
    assert response.status_code == 404, (
        f"Expected 404 for /redoc (ReDoc UI disabled), got {response.status_code}."
    )


# ---------------------------------------------------------------------------
# Positive test: API routes are still accessible after schema is disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l2_api_routes_still_functional(prod_client):
    """Positive: disabling the schema docs does not disable the API itself."""
    response = await prod_client.get("/api/v1/health/live")
    assert response.status_code == 200, (
        f"Health endpoint unexpectedly unreachable (got {response.status_code}). "
        f"Disabling OpenAPI schema must not disable normal API routes."
    )


# ---------------------------------------------------------------------------
# Contrast: schema IS exposed in local mode (by design)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_l2_schema_accessible_in_local_mode(client):
    """
    Contrast: /openapi.json IS accessible in local dev mode (PEARL_LOCAL=1).

    This is intentional — developers need the schema. The production control
    disables it via expose_openapi=False. This test documents that distinction.
    """
    response = await client.get("/openapi.json")
    assert response.status_code == 200, (
        f"Expected /openapi.json to be accessible in local mode, got {response.status_code}. "
        f"Local dev mode should expose the schema for developer convenience."
    )
