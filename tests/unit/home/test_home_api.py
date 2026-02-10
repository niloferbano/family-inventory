import pytest
from sqlalchemy import select

from app.apis.homes.models import Home


@pytest.mark.asyncio
async def test_get_home_by_owner(client, auth_headers):
    create = await client.post(
        "/homes/",
        json={"name": "Owner Home"},
        headers=auth_headers,
    )
    home_id = create.json()["id"]

    res = await client.get(f"/homes/{home_id}", headers=auth_headers)

    assert res.status_code == 200
    body = res.json()
    assert body["id"] == home_id
    assert body["name"] == "Owner Home"


@pytest.mark.asyncio
async def test_delete_home_removes_record(client, auth_headers, db_session):
    create = await client.post(
        "/homes/",
        json={"name": "Delete Home"},
        headers=auth_headers,
    )
    home_id = create.json()["id"]

    res = await client.delete(f"/homes/{home_id}", headers=auth_headers)

    assert res.status_code == 204

    check = await db_session.execute(select(Home.id).where(Home.id == home_id))
    assert check.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_admin_homes_requires_admin(client, auth_headers):
    res = await client.get("/homes/admin/homes", headers=auth_headers)

    assert res.status_code == 403
    body = res.json()
    assert body["detail"] == "Permission denied"


@pytest.mark.asyncio
async def test_admin_can_list_homes(client, admin_headers):
    await client.post(
        "/homes/",
        json={"name": "Admin Home"},
        headers=admin_headers,
    )

    res = await client.get("/homes/admin/homes", headers=admin_headers)

    assert res.status_code == 200
    body = res.json()
    assert "results" in body
    assert body["count"] >= 1
