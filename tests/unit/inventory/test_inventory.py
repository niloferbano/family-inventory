from datetime import date, timedelta

import pytest

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.inventory.models import InventoryCategory, InventoryItem


@pytest.mark.asyncio
async def test_owner_adds_single_item(client, db_session, auth_headers):
    """Owner can add a single inventory item."""
    # Create a home
    home = Home(name="Kitchen Home")
    db_session.add(home)
    await db_session.flush()

    # Assign owner
    await db_session.execute(
        """
        INSERT INTO home_users (user_id, home_id, user_type)
        VALUES (:uid, :hid, 'owner')
        """,
        {"uid": 1, "hid": home.id},
    )

    res = await client.post(
        f"/homes/{home.id}/inventory",
        json={
            "name": "Milk",
            "category": "kitchen",
            "quantity": 2,
            "unit": "liters",
        },
        headers=auth_headers,
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "Milk"
    assert body["category"] == "kitchen"
    assert body["quantity"] == 2


@pytest.mark.asyncio
async def test_owner_adds_multiple_items(client, db_session, auth_headers):
    """Owner can add multiple items at once."""
    home = Home(name="Bulk Home")
    db_session.add(home)
    await db_session.flush()

    # Owner link
    db_session.add(HomeUser(user_id=1, home_id=home.id, user_type=UserType.OWNER))
    await db_session.flush()

    payload = [
        {"name": "Soap", "category": "bathroom", "quantity": 3},
        {"name": "Detergent", "category": "cleaning", "quantity": 1},
    ]

    res = await client.post(
        f"/homes/{home.id}/inventory",
        json=payload,
        headers=auth_headers,
    )

    assert res.status_code == 200
    items = res.json()
    assert len(items) == 2
    assert {i["name"] for i in items} == {"Soap", "Detergent"}


@pytest.mark.asyncio
async def test_non_owner_cannot_add_items(client, db_session, auth_headers):
    """Residents / guests are forbidden from adding items."""
    home = Home(name="Restricted Home")
    db_session.add(home)
    await db_session.flush()

    # Add user as RESIDENCE not OWNER
    db_session.add(HomeUser(user_id=1, home_id=home.id, user_type=UserType.RESIDENCE))
    await db_session.flush()

    res = await client.post(
        f"/homes/{home.id}/inventory",
        json={
            "name": "Shampoo",
            "category": "bathroom",
            "quantity": 1,
        },
        headers=auth_headers,
    )

    assert res.status_code == 403


@pytest.mark.asyncio
async def test_filter_expired_items(client, db_session, auth_headers):
    """Expired item filtering using ?expired=true."""
    home = Home(name="Expiry Home")
    db_session.add(home)
    await db_session.flush()

    db_session.add(HomeUser(user_id=1, home_id=home.id, user_type=UserType.OWNER))

    today = date.today()
    expired_date = today - timedelta(days=2)
    future_date = today + timedelta(days=10)

    expired_item = InventoryItem(
        home_id=home.id,
        created_by=1,
        name="Old Bread",
        category=InventoryCategory.KITCHEN,
        expiry_date=expired_date,
    )
    fresh_item = InventoryItem(
        home_id=home.id,
        created_by=1,
        name="Fresh Milk",
        category=InventoryCategory.KITCHEN,
        expiry_date=future_date,
    )

    db_session.add_all([expired_item, fresh_item])
    await db_session.flush()

    res = await client.get(
        f"/homes/{home.id}/inventory?expired=true",
        headers=auth_headers,
    )

    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["name"] == "Old Bread"


@pytest.mark.asyncio
async def test_filter_by_category(client, db_session, auth_headers):
    """Filter items by category using ?category=bathroom."""
    home = Home(name="Category Home")
    db_session.add(home)
    await db_session.flush()

    db_session.add(HomeUser(user_id=1, home_id=home.id, user_type=UserType.OWNER))

    items = [
        InventoryItem(
            home_id=home.id,
            created_by=1,
            name="Shampoo",
            category=InventoryCategory.BATHROOM,
        ),
        InventoryItem(
            home_id=home.id,
            created_by=1,
            name="Pasta",
            category=InventoryCategory.KITCHEN,
        ),
    ]

    db_session.add_all(items)
    await db_session.flush()

    res = await client.get(
        f"/homes/{home.id}/inventory?category=bathroom",
        headers=auth_headers,
    )

    assert res.status_code == 200
    results = res.json()
    assert len(results) == 1
    assert results[0]["name"] == "Shampoo"
