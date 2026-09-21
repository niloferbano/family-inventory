from uuid import uuid4

import pytest
from sqlalchemy import select

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.household_categories.models import HouseholdCategory
from app.apis.users.models import User


async def setup_home(session, role, admin=False):
    user = await session.scalar(select(User).where(User.email == "auth@example.com"))
    user.is_admin = admin
    home = Home(name=f"Category home {uuid4().hex}")
    session.add(home)
    await session.flush()
    if role:
        session.add(HomeUser(user_id=user.id, home_id=home.id, user_type=role))
    await session.commit()
    return home


@pytest.mark.asyncio
async def test_unauthenticated_category_creation(client):
    response = await client.post(
        f"/homes/{uuid4()}/categories", json={"name": "Kitchen"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,admin,expected",
    [
        (None, False, 403),
        (None, True, 403),
        (UserType.GUEST, False, 403),
        (UserType.RESIDENCE, False, 403),
        (UserType.OWNER, False, 201),
        (UserType.RESIDENCE, True, 201),
    ],
)
async def test_category_permissions(
    client, db_session, auth_headers, role, admin, expected
):
    home = await setup_home(db_session, role, admin)
    response = await client.post(
        f"/homes/{home.id}/categories", headers=auth_headers, json={"name": "Kitchen"}
    )
    assert response.status_code == expected
    categories = (await db_session.scalars(select(HouseholdCategory))).all()
    assert len(categories) == (1 if expected == 201 else 0)


@pytest.mark.asyncio
async def test_owner_of_other_home_cannot_create(client, db_session, auth_headers):
    await setup_home(db_session, UserType.OWNER)
    other = Home(name="Not owned")
    db_session.add(other)
    await db_session.commit()
    response = await client.post(
        f"/homes/{other.id}/categories", headers=auth_headers, json={"name": "Kitchen"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", " \t\n ", "x" * 61])
async def test_invalid_names(client, db_session, auth_headers, name):
    home = await setup_home(db_session, UserType.OWNER)
    response = await client.post(
        f"/homes/{home.id}/categories", headers=auth_headers, json={"name": name}
    )
    assert response.status_code == 422
    assert (await db_session.scalars(select(HouseholdCategory))).all() == []


@pytest.mark.asyncio
async def test_trim_duplicates_and_create_inventory(client, db_session, auth_headers):
    home = await setup_home(db_session, UserType.OWNER)
    url = f"/homes/{home.id}/categories"
    response = await client.post(
        url, headers=auth_headers, json={"name": "  Kitchen \t"}
    )
    assert response.status_code == 201
    category = response.json()
    assert category["name"] == "Kitchen"
    stored = await db_session.scalar(select(HouseholdCategory))
    assert stored.name == "Kitchen"
    response = await client.post(url, headers=auth_headers, json={"name": " Kitchen "})
    assert response.status_code == 409
    assert response.json()["message"]
    other = await setup_home(db_session, UserType.OWNER)
    response = await client.post(
        f"/homes/{other.id}/categories", headers=auth_headers, json={"name": "Kitchen"}
    )
    assert response.status_code == 201
    response = await client.post(
        url, headers=auth_headers, json={"name": "  " + "x" * 60 + "  "}
    )
    assert response.status_code == 201
    assert response.json()["name"] == "x" * 60
    product = await client.post(
        "/products", headers=auth_headers, json={"name": "Milk"}
    )
    assert product.status_code == 201
    response = await client.post(
        f"/inventory/{home.id}",
        headers=auth_headers,
        json=[
            {
                "product_id": product.json()["id"],
                "household_category_id": category["id"],
                "quantity": 2,
                "unit": "liters",
            }
        ],
    )
    assert response.status_code == 200
    assert response.json()[0]["household_category_id"] == category["id"]
    assert response.json()[0]["quantity"] == 2
