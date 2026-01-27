from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.inventory.models import InventoryCategory, InventoryItem
from app.apis.users.models import User


async def _get_auth_user_id(db_session) -> str:
    result = await db_session.execute(
        select(User.id).where(User.email == "auth@example.com")
    )
    return result.scalar_one()


@pytest.mark.asyncio
async def test_owner_adds_single_item(client, db_session, auth_headers):
    home = Home(name="Kitchen Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )
    await db_session.commit()

    payload = [
        {
            "name": "Milk",
            "category": "kitchen",
            "quantity": 2,
            "unit": "liters",
        }
    ]

    res = await client.post(
        f"/inventory/{home.id}",
        json=payload,
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert isinstance(body, list)
    assert body[0]["name"] == "Milk"
    assert body[0]["category"] == "kitchen"
    assert body[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_owner_adds_multiple_items(client, db_session, auth_headers):
    home = Home(name="Bulk Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )
    await db_session.commit()

    payload = [
        {"name": "Soap", "category": "bathroom", "quantity": 3},
        {"name": "Detergent", "category": "cleaning", "quantity": 1},
    ]

    res = await client.post(
        f"/inventory/{home.id}",
        json=payload,
        headers=auth_headers,
    )

    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    assert {i["name"] for i in items} == {"Soap", "Detergent"}


@pytest.mark.asyncio
async def test_duplicate_name_returns_conflict(client, db_session, auth_headers):
    home = Home(name="Conflict Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )
    await db_session.commit()

    first = await client.post(
        f"/inventory/{home.id}",
        json=[{"name": "Milk", "category": "kitchen", "quantity": 1}],
        headers=auth_headers,
    )
    assert first.status_code == 200

    conflict = await client.post(
        f"/inventory/{home.id}",
        json=[{"name": "Milk", "category": "kitchen", "quantity": 1}],
        headers=auth_headers,
    )

    assert conflict.status_code == 409
    body = conflict.json()
    assert body["error"] == "INVENTORY_ITEM_NAME_CONFLICT"
    assert "Milk" in body["details"]["names"]


@pytest.mark.asyncio
async def test_non_owner_cannot_add_items(client, db_session, auth_headers):
    home = Home(name="Restricted Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.RESIDENCE)
    )
    await db_session.commit()

    res = await client.post(
        f"/inventory/{home.id}",
        json=[{"name": "Shampoo", "category": "bathroom", "quantity": 1}],
        headers=auth_headers,
    )

    assert res.status_code == 403
    body = res.json()
    assert body["error"] == "INVENTORY_ACCESS_DENIED"


@pytest.mark.asyncio
async def test_filter_expired_items(client, db_session, auth_headers):
    home = Home(name="Expiry Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )

    today = date.today()
    expired_date = today - timedelta(days=2)
    future_date = today + timedelta(days=10)

    items = [
        InventoryItem(
            home_id=home.id,
            created_by=auth_user_id,
            name="Old Bread",
            category=InventoryCategory.KITCHEN,
            expiry_date=expired_date,
        ),
        InventoryItem(
            home_id=home.id,
            created_by=auth_user_id,
            name="Fresh Milk",
            category=InventoryCategory.KITCHEN,
            expiry_date=future_date,
        ),
    ]

    db_session.add_all(items)
    await db_session.commit()

    res = await client.get(
        f"/inventory/{home.id}?expiry=expired",
        headers=auth_headers,
    )

    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 1
    assert results[0]["name"] == "Old Bread"


@pytest.mark.asyncio
async def test_filter_expiring_soon_items(client, db_session, auth_headers):
    home = Home(name="Expiring Soon Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )

    today = date.today()
    soon = today + timedelta(days=2)
    later = today + timedelta(days=20)

    db_session.add_all(
        [
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Soon Expiry",
                category=InventoryCategory.OTHER,
                expiry_date=soon,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Much Later",
                category=InventoryCategory.OTHER,
                expiry_date=later,
            ),
        ]
    )
    await db_session.commit()

    res = await client.get(
        f"/inventory/{home.id}?expiry=expiring_soon&days=5",
        headers=auth_headers,
    )

    assert res.status_code == 200
    results = res.json()["results"]
    assert [item["name"] for item in results] == ["Soon Expiry"]


@pytest.mark.asyncio
async def test_filter_by_multiple_categories(client, db_session, auth_headers):
    home = Home(name="Category Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )

    db_session.add_all(
        [
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Shampoo",
                category=InventoryCategory.BATHROOM,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Detergent",
                category=InventoryCategory.CLEANING,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Rice",
                category=InventoryCategory.KITCHEN,
            ),
        ]
    )
    await db_session.commit()

    res = await client.get(
        f"/inventory/{home.id}?category=bathroom&category=cleaning",
        headers=auth_headers,
    )

    assert res.status_code == 200
    names = {item["name"] for item in res.json()["results"]}
    assert names == {"Shampoo", "Detergent"}
