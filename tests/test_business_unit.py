"""Tests for Business Unit CRUD operations and framework requirement derivation.

Covers:
- GET /business-units returns empty list initially
- POST /business-units creates a BU
- GET /business-units/{bu_id} returns the created BU
- PATCH /business-units/{bu_id} updates name/description
- DELETE /business-units/{bu_id} returns 204
- POST /business-units/{bu_id}/frameworks derives FrameworkRequirementRows
- GET /business-units/{bu_id}/requirements lists requirements after derivation
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pearl.db.models.org import OrgRow
from pearl.services.id_generator import generate_id


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _seed_org(db_session: AsyncSession, org_id: str = "org_test_bu") -> str:
    """Insert a minimal OrgRow so BU foreign key constraint passes."""
    from sqlalchemy import select
    result = await db_session.execute(select(OrgRow).where(OrgRow.org_id == org_id))
    existing = result.scalar_one_or_none()
    if not existing:
        row = OrgRow(org_id=org_id, name="Test Org", slug=f"test-org-{org_id[-4:]}", settings={})
        db_session.add(row)
        await db_session.commit()
    return org_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_business_units_empty(client, db_session):
    """GET /business-units returns an empty list when no BUs exist."""
    org_id = await _seed_org(db_session, "org_bu_list_empty")
    r = await client.get("/api/v1/business-units", params={"org_id": org_id})
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_create_business_unit(client, db_session):
    """POST /business-units creates a new BU and returns it."""
    org_id = await _seed_org(db_session, "org_bu_create")
    payload = {
        "org_id": org_id,
        "name": "Platform Engineering",
        "description": "Core platform team",
        "framework_selections": [],
    }
    r = await client.post("/api/v1/business-units", json=payload)
    assert r.status_code == 201
    data = r.json()
    assert data["org_id"] == org_id
    assert data["name"] == "Platform Engineering"
    assert data["description"] == "Core platform team"
    assert data["bu_id"].startswith("bu_")


@pytest.mark.asyncio
async def test_create_business_unit_missing_fields(client, db_session):
    """POST /business-units returns 400 when org_id or name is missing."""
    r = await client.post("/api/v1/business-units", json={"name": "NoOrg"})
    assert r.status_code == 400

    await _seed_org(db_session, "org_bu_noname")
    r2 = await client.post("/api/v1/business-units", json={"org_id": "org_bu_noname"})
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_create_business_unit_duplicate_name(client, db_session):
    """POST /business-units returns 409 when a BU with the same name exists."""
    org_id = await _seed_org(db_session, "org_bu_dup")
    payload = {"org_id": org_id, "name": "Duplicate BU"}
    r1 = await client.post("/api/v1/business-units", json=payload)
    assert r1.status_code == 201

    r2 = await client.post("/api/v1/business-units", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_get_business_unit(client, db_session):
    """GET /business-units/{bu_id} returns the created BU."""
    org_id = await _seed_org(db_session, "org_bu_get")
    create_r = await client.post(
        "/api/v1/business-units",
        json={"org_id": org_id, "name": "Security BU"},
    )
    bu_id = create_r.json()["bu_id"]

    r = await client.get(f"/api/v1/business-units/{bu_id}")
    assert r.status_code == 200
    data = r.json()
    assert data["bu_id"] == bu_id
    assert data["name"] == "Security BU"


@pytest.mark.asyncio
async def test_get_business_unit_not_found(client):
    """GET /business-units/{bu_id} returns 404 for a non-existent BU."""
    r = await client.get("/api/v1/business-units/bu_does_not_exist")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_business_unit(client, db_session):
    """PATCH /business-units/{bu_id} updates name and description."""
    org_id = await _seed_org(db_session, "org_bu_update")
    create_r = await client.post(
        "/api/v1/business-units",
        json={"org_id": org_id, "name": "Old Name", "description": "Old desc"},
    )
    bu_id = create_r.json()["bu_id"]

    r = await client.patch(
        f"/api/v1/business-units/{bu_id}",
        json={"name": "New Name", "description": "Updated description"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["name"] == "New Name"
    assert data["description"] == "Updated description"


@pytest.mark.asyncio
async def test_delete_business_unit(client, db_session):
    """DELETE /business-units/{bu_id} returns 204 and removes the BU."""
    org_id = await _seed_org(db_session, "org_bu_delete")
    create_r = await client.post(
        "/api/v1/business-units",
        json={"org_id": org_id, "name": "To Be Deleted"},
    )
    bu_id = create_r.json()["bu_id"]

    del_r = await client.delete(f"/api/v1/business-units/{bu_id}")
    assert del_r.status_code == 204

    # Confirm it is gone
    get_r = await client.get(f"/api/v1/business-units/{bu_id}")
    assert get_r.status_code == 404


@pytest.mark.asyncio
async def test_derive_framework_requirements(client, db_session):
    """POST /business-units/{bu_id}/frameworks creates FrameworkRequirementRows."""
    org_id = await _seed_org(db_session, "org_bu_frameworks")
    create_r = await client.post(
        "/api/v1/business-units",
        json={"org_id": org_id, "name": "SLSA BU"},
    )
    bu_id = create_r.json()["bu_id"]

    r = await client.post(
        f"/api/v1/business-units/{bu_id}/frameworks",
        json={"framework_selections": ["slsa"]},
    )
    assert r.status_code == 201
    data = r.json()
    assert data["bu_id"] == bu_id
    assert "slsa" in data["frameworks"]
    assert data["requirements_created"] > 0


@pytest.mark.asyncio
async def test_derive_framework_requirements_idempotent(client, db_session):
    """Calling /frameworks twice replaces requirements without duplicating them."""
    org_id = await _seed_org(db_session, "org_bu_idem")
    create_r = await client.post(
        "/api/v1/business-units",
        json={"org_id": org_id, "name": "Idempotent BU"},
    )
    bu_id = create_r.json()["bu_id"]

    r1 = await client.post(
        f"/api/v1/business-units/{bu_id}/frameworks",
        json={"framework_selections": ["slsa"]},
    )
    count1 = r1.json()["requirements_created"]

    r2 = await client.post(
        f"/api/v1/business-units/{bu_id}/frameworks",
        json={"framework_selections": ["slsa"]},
    )
    count2 = r2.json()["requirements_created"]

    # Second call should produce the same count (old ones deleted, new ones created)
    assert count1 == count2

    # Listing requirements should reflect the latest derivation
    list_r = await client.get(f"/api/v1/business-units/{bu_id}/requirements")
    assert list_r.status_code == 200
    assert len(list_r.json()) == count2


@pytest.mark.asyncio
async def test_list_bu_requirements(client, db_session):
    """GET /business-units/{bu_id}/requirements lists requirements after derivation."""
    org_id = await _seed_org(db_session, "org_bu_reqs_list")
    create_r = await client.post(
        "/api/v1/business-units",
        json={"org_id": org_id, "name": "OWASP BU"},
    )
    bu_id = create_r.json()["bu_id"]

    await client.post(
        f"/api/v1/business-units/{bu_id}/frameworks",
        json={"framework_selections": ["owasp_llm"]},
    )

    r = await client.get(f"/api/v1/business-units/{bu_id}/requirements")
    assert r.status_code == 200
    reqs = r.json()
    assert len(reqs) > 0

    # Each requirement should have the expected fields
    req = reqs[0]
    assert "requirement_id" in req
    assert req["requirement_id"].startswith("freq_")
    assert req["bu_id"] == bu_id
    assert req["framework"] == "owasp_llm"
    assert "control_id" in req
    assert "applies_to_transitions" in req
    assert req["requirement_level"] in ("mandatory", "recommended")
    assert "evidence_type" in req


@pytest.mark.asyncio
async def test_list_bu_requirements_empty_before_derivation(client, db_session):
    """GET /business-units/{bu_id}/requirements returns empty list before derivation."""
    org_id = await _seed_org(db_session, "org_bu_noreqs")
    create_r = await client.post(
        "/api/v1/business-units",
        json={"org_id": org_id, "name": "Empty BU"},
    )
    bu_id = create_r.json()["bu_id"]

    r = await client.get(f"/api/v1/business-units/{bu_id}/requirements")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_list_business_units_by_org(client, db_session):
    """GET /business-units?org_id=X only returns BUs for that org."""
    org_a = await _seed_org(db_session, "org_bu_list_a")
    org_b = await _seed_org(db_session, "org_bu_list_b")

    await client.post("/api/v1/business-units", json={"org_id": org_a, "name": "BU Alpha"})
    await client.post("/api/v1/business-units", json={"org_id": org_b, "name": "BU Beta"})

    r_a = await client.get("/api/v1/business-units", params={"org_id": org_a})
    assert r_a.status_code == 200
    names_a = {bu["name"] for bu in r_a.json()}
    assert "BU Alpha" in names_a
    assert "BU Beta" not in names_a
