from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.apis.homes.models import Home
from app.apis.homeuser.models import HomeUser, UserType
from app.apis.household_categories.models import HouseholdCategory
from app.apis.inventory.models import InventoryItem
from app.apis.product.models import Product
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


async def _add_product(db_session, name: str) -> Product:
    product = Product(name=name)
    db_session.add(product)
    await db_session.flush()
    return product


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
    milk = await _add_product(db_session, "Milk")
    await db_session.commit()

    payload = [
        {
            "product_id": str(milk.id),
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
    assert body[0]["product_id"] == str(milk.id)
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
    soap = await _add_product(db_session, "Soap")
    detergent = await _add_product(db_session, "Detergent")
    await db_session.commit()

    payload = [
        {
            "product_id": str(soap.id),
            "household_category_id": str(bathroom.id),
            "quantity": 3,
        },
        {
            "product_id": str(detergent.id),
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
    assert {i["product_id"] for i in items} == {str(soap.id), str(detergent.id)}


@pytest.mark.asyncio
async def test_add_items_with_unknown_product_returns_error(
    client, db_session, auth_headers
):
    from uuid import uuid4

    home = Home(name="Unknown Product Home")
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
            "product_id": str(uuid4()),
            "household_category_id": str(kitchen.id),
            "quantity": 1,
        }
    ]

    res = await client.post(
        f"/inventory/{home.id}",
        json=payload,
        headers=auth_headers,
    )

    assert res.status_code == 404
    body = res.json()
    assert body["error"] == "PRODUCT_NOT_FOUND"


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
    shampoo = await _add_product(db_session, "Shampoo")
    await db_session.commit()

    res = await client.post(
        f"/inventory/{home.id}",
        json=[
            {
                "product_id": str(shampoo.id),
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
    old_bread = await _add_product(db_session, "Old Bread")
    fresh_milk = await _add_product(db_session, "Fresh Milk")

    today = date.today()
    expired_date = today - timedelta(days=2)
    future_date = today + timedelta(days=10)

    items = [
        InventoryItem(
            home_id=home.id,
            created_by=auth_user_id,
            product_id=old_bread.id,
            household_category_id=kitchen.id,
            expiry_date=expired_date,
        ),
        InventoryItem(
            home_id=home.id,
            created_by=auth_user_id,
            product_id=fresh_milk.id,
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
    assert results[0]["product_id"] == str(old_bread.id)


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
    soon_expiry = await _add_product(db_session, "Soon Expiry")
    much_later = await _add_product(db_session, "Much Later")

    today = date.today()
    soon = today + timedelta(days=2)
    later = today + timedelta(days=20)

    db_session.add_all(
        [
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                product_id=soon_expiry.id,
                household_category_id=other.id,
                expiry_date=soon,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                product_id=much_later.id,
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
    assert [item["product_id"] for item in results] == [str(soon_expiry.id)]


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
    shampoo = await _add_product(db_session, "Shampoo")
    detergent = await _add_product(db_session, "Detergent")
    rice = await _add_product(db_session, "Rice")

    db_session.add_all(
        [
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                product_id=shampoo.id,
                household_category_id=bathroom.id,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                product_id=detergent.id,
                household_category_id=cleaning.id,
            ),
            InventoryItem(
                home_id=home.id,
                created_by=auth_user_id,
                product_id=rice.id,
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
    product_ids = {item["product_id"] for item in res.json()["results"]}
    assert product_ids == {str(shampoo.id), str(detergent.id)}


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
    rice = await _add_product(db_session, "Rice")

    item = InventoryItem(
        home_id=home.id,
        created_by=auth_user_id,
        product_id=rice.id,
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
async def test_update_item_with_unknown_product_returns_error(
    client, db_session, auth_headers
):
    from uuid import uuid4

    home = Home(name="Update Unknown Product Home")
    db_session.add(home)
    await db_session.flush()
    auth_user_id = await _get_auth_user_id(db_session)
    db_session.add(
        HomeUser(user_id=auth_user_id, home_id=home.id, user_type=UserType.OWNER)
    )
    kitchen = await _add_category(db_session, home.id, "Kitchen")
    rice = await _add_product(db_session, "Rice")

    item = InventoryItem(
        home_id=home.id,
        created_by=auth_user_id,
        product_id=rice.id,
        household_category_id=kitchen.id,
        quantity=1,
    )
    db_session.add(item)
    await db_session.commit()

    res = await client.patch(
        f"/inventory/{home.id}/{item.id}",
        json={"product_id": str(uuid4())},
        headers=auth_headers,
    )

    assert res.status_code == 404
    body = res.json()
    assert body["error"] == "PRODUCT_NOT_FOUND"


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
    old_item = await _add_product(db_session, "Old Item")

    item = InventoryItem(
        home_id=home.id,
        created_by=auth_user_id,
        product_id=old_item.id,
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


@pytest.mark.asyncio
async def test_category_choices_and_cross_home_validation(
    client, db_session, auth_headers
):
    from uuid import uuid4

    home = Home(name="Allowed")
    other = Home(name="Other")
    db_session.add_all([home, other])
    await db_session.flush()
    user_id = await _get_auth_user_id(db_session)
    db_session.add(HomeUser(user_id=user_id, home_id=home.id, user_type=UserType.OWNER))
    own = await _add_category(db_session, home.id, "Kitchen")
    foreign = await _add_category(db_session, other.id, "Private category")
    valid_product = await _add_product(db_session, "Valid")
    invalid_product = await _add_product(db_session, "Invalid")
    await db_session.commit()

    choices = await client.get(f"/inventory/{home.id}/categories", headers=auth_headers)
    assert choices.status_code == 200
    assert [(c["id"], c["name"]) for c in choices.json()] == [(str(own.id), "Kitchen")]
    denied = await client.get(f"/inventory/{other.id}/categories", headers=auth_headers)
    assert denied.status_code == 403

    for invalid in (foreign.id, uuid4()):
        response = await client.post(
            f"/inventory/{home.id}",
            headers=auth_headers,
            json=[
                {"product_id": str(valid_product.id), "household_category_id": str(own.id)},
                {"product_id": str(invalid_product.id), "household_category_id": str(invalid)},
            ],
        )
        assert response.status_code == 422
    assert (
        await db_session.scalars(
            select(InventoryItem).where(InventoryItem.home_id == home.id)
        )
    ).all() == []

    response = await client.post(
        f"/inventory/{home.id}",
        headers=auth_headers,
        json=[
            {"product_id": str(valid_product.id), "household_category_id": str(own.id)},
        ],
    )
    assert response.status_code == 200
    item_id = response.json()[0]["id"]
    for invalid in (str(foreign.id), None):
        response = await client.patch(
            f"/inventory/{home.id}/{item_id}",
            headers=auth_headers,
            json={"household_category_id": invalid},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize("delete_first", [False, True])
async def test_category_deletion_races_inventory_write(
    client, db_session, mock_db, auth_headers, monkeypatch, operation, delete_first
):
    from sqlalchemy import delete, text
    from sqlalchemy.exc import DBAPIError, IntegrityError

    from app.apis.household_categories.repository import HouseholdCategoryRepository

    home = Home(name="Category race")
    db_session.add(home)
    await db_session.flush()
    user_id = await _get_auth_user_id(db_session)
    db_session.add(HomeUser(user_id=user_id, home_id=home.id, user_type=UserType.OWNER))
    original = await _add_category(db_session, home.id, "Original")
    target = await _add_category(db_session, home.id, "Target")
    existing_product = await _add_product(db_session, "Existing")
    new_product = await _add_product(db_session, "New")
    item = InventoryItem(
        home_id=home.id,
        product_id=existing_product.id,
        household_category_id=original.id,
    )
    db_session.add(item)
    await db_session.commit()
    target_id = target.id
    original_id = original.id
    item_id = item.id
    new_product_id = new_product.id
    lock = HouseholdCategoryRepository.lock_for_inventory
    deletion_attempted = False

    async def delete_target():
        async with mock_db.begin() as session:
            await session.execute(text("SET LOCAL lock_timeout = '200ms'"))
            await session.execute(
                delete(HouseholdCategory).where(HouseholdCategory.id == target_id)
            )

    async def racing_lock(repo, home_id, category_ids):
        nonlocal deletion_attempted
        if delete_first:
            # Delete commits while the inventory request is in progress,
            # before the category validation query acquires its lock.
            await delete_target()
        categories = await lock(repo, home_id, category_ids)
        if not delete_first:
            # A second real transaction attempts deletion in the gap between
            # category validation and inventory insertion/update.
            with pytest.raises(DBAPIError) as exc:
                await delete_target()
            assert getattr(exc.value.orig, "sqlstate", None) == "55P03"
        deletion_attempted = True
        return categories

    monkeypatch.setattr(HouseholdCategoryRepository, "lock_for_inventory", racing_lock)
    if operation == "create":
        response = await client.post(
            f"/inventory/{home.id}",
            headers=auth_headers,
            json=[
                {"product_id": str(new_product_id), "household_category_id": str(target_id)},
            ],
        )
    else:
        response = await client.patch(
            f"/inventory/{home.id}/{item_id}",
            headers=auth_headers,
            json={"household_category_id": str(target_id)},
        )
    assert deletion_attempted
    assert response.status_code == (422 if delete_first else 200)
    async with mock_db.begin() as session:
        updated = await session.get(InventoryItem, item_id)
        assert updated.household_category_id == (
            target_id if operation == "update" and not delete_first else original_id
        )
        created = await session.scalar(
            select(InventoryItem).where(
                InventoryItem.home_id == home.id,
                InventoryItem.product_id == new_product_id,
            )
        )
        assert (created is not None) == (operation == "create" and not delete_first)
    if not delete_first:
        # Once the writer commits, the foreign key prevents deletion of the
        # now-referenced category instead of merely waiting on its lock.
        with pytest.raises(IntegrityError) as exc:
            await delete_target()
        assert getattr(exc.value.orig, "sqlstate", None) == "23503"
