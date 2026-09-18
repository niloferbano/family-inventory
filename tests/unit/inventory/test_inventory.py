from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.household_categories.models import HouseholdCategory
from app.apis.inventory.models import InventoryItem
from app.apis.users.models import User


async def _get_auth_user_id(db_session) -> str:
    result = await db_session.execute(
        select(User.id).where(User.email == "auth@example.com")
    )
    return result.scalar_one()


async def _add_category(db_session, home_id, name: str) -> HouseholdCategory:
    category = HouseholdCategory(home_id=home_id, name=name)
    db_session.add(category)
    await db_session.flush()
    return category


@pytest.mark.asyncio
async def test_owner_adds_single_item(client, db_session, auth_headers):
    home = Home(name="Kitchen Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )
    kitchen = await _add_category(db_session, home.id, "Kitchen")
    await db_session.commit()

    payload = [
        {
            "name": "Milk",
            "household_category_id": str(kitchen.id),
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
    assert body[0]["household_category_id"] == str(kitchen.id)
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
    bathroom = await _add_category(db_session, home.id, "Bathroom")
    cleaning = await _add_category(db_session, home.id, "Cleaning")
    await db_session.commit()

    payload = [
        {
            "name": "Soap",
            "household_category_id": str(bathroom.id),
            "quantity": 3,
        },
        {
            "name": "Detergent",
            "household_category_id": str(cleaning.id),
            "quantity": 1,
        },
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
    kitchen = await _add_category(db_session, home.id, "Kitchen")
    await db_session.commit()

    payload = [
        {"name": "Milk", "household_category_id": str(kitchen.id), "quantity": 1}
    ]

    first = await client.post(
        f"/inventory/{home.id}",
        json=payload,
        headers=auth_headers,
    )
    assert first.status_code == 200

    conflict = await client.post(
        f"/inventory/{home.id}",
        json=payload,
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
    bathroom = await _add_category(db_session, home.id, "Bathroom")
    await db_session.commit()

    res = await client.post(
        f"/inventory/{home.id}",
        json=[
            {
                "name": "Shampoo",
                "household_category_id": str(bathroom.id),
                "quantity": 1,
            }
        ],
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
    kitchen = await _add_category(db_session, home.id, "Kitchen")

    today = date.today()
    expired_date = today - timedelta(days=2)
    future_date = today + timedelta(days=10)

    items = [
        InventoryItem(
            home_id=home.id,
            created_by=auth_user_id,
            name="Old Bread",
            household_category_id=kitchen.id,
            expiry_date=expired_date,
        ),
        InventoryItem(
            home_id=home.id,
            created_by=auth_user_id,
            name="Fresh Milk",
            household_category_id=kitchen.id,
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
    other = await _add_category(db_session, home.id, "Other")

    today = date.today()
    soon = today + timedelta(days=2)
    later = today + timedelta(days=20)

    db_session.add_all(
        [
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Soon Expiry",
                household_category_id=other.id,
                expiry_date=soon,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Much Later",
                household_category_id=other.id,
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
    bathroom = await _add_category(db_session, home.id, "Bathroom")
    cleaning = await _add_category(db_session, home.id, "Cleaning")
    kitchen = await _add_category(db_session, home.id, "Kitchen")

    db_session.add_all(
        [
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Shampoo",
                household_category_id=bathroom.id,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Detergent",
                household_category_id=cleaning.id,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                name="Rice",
                household_category_id=kitchen.id,
            ),
        ]
    )
    await db_session.commit()

    res = await client.get(
        f"/inventory/{home.id}?household_category_id={bathroom.id}"
        f"&household_category_id={cleaning.id}",
        headers=auth_headers,
    )

    assert res.status_code == 200
    names = {item["name"] for item in res.json()["results"]}
    assert names == {"Shampoo", "Detergent"}


@pytest.mark.asyncio
async def test_owner_can_update_item(client, db_session, auth_headers):
    home = Home(name="Update Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )
    kitchen = await _add_category(db_session, home.id, "Kitchen")

    item = InventoryItem(
        home_id=home.id,
        created_by=auth_user_id,
        name="Rice",
        household_category_id=kitchen.id,
        quantity=1,
    )
    db_session.add(item)
    await db_session.commit()

    res = await client.patch(
        f"/inventory/{home.id}/{item.id}",
        json={"quantity": 5, "notes": "restock"},
        headers=auth_headers,
    )

    assert res.status_code == 200
    body = res.json()
    assert body["quantity"] == 5
    assert body["notes"] == "restock"


@pytest.mark.asyncio
async def test_owner_can_delete_item(client, db_session, auth_headers):
    home = Home(name="Delete Inventory Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )
    other = await _add_category(db_session, home.id, "Other")

    item = InventoryItem(
        home_id=home.id,
        created_by=auth_user_id,
        name="Old Item",
        household_category_id=other.id,
        quantity=1,
    )
    db_session.add(item)
    await db_session.commit()

    res = await client.delete(
        f"/inventory/{home.id}/{item.id}",
        headers=auth_headers,
    )

    assert res.status_code == 204

    exists = await db_session.execute(
        select(InventoryItem.id).where(InventoryItem.id == item.id)
    )
    assert exists.scalar_one_or_none() is None
