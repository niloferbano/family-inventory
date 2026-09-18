import pytest

from app.apis.homes.models import Home
from app.apis.household_categories.models import HouseholdCategory
from app.apis.inventory.models import InventoryItem
from app.apis.product.models import Product


@pytest.mark.asyncio
async def test_inventory_item_product_is_nullable(mock_db):
    async with mock_db.begin() as session:
        home = Home(name="No Product Yet")
        session.add(home)
        await session.flush()
        category = HouseholdCategory(home_id=home.id, name="Kitchen")
        session.add(category)
        await session.flush()

        item = InventoryItem(
            home_id=home.id,
            name="Legacy Milk",
            household_category_id=category.id,
        )
        session.add(item)
        await session.flush()
        item_id = item.id
        assert item.product_id is None

    async with mock_db.begin() as session:
        item = await session.get(InventoryItem, item_id)
        assert item.product_id is None
        assert item.product is None


@pytest.mark.asyncio
async def test_inventory_item_can_link_to_product(mock_db):
    async with mock_db.begin() as session:
        home = Home(name="With Product")
        session.add(home)
        await session.flush()
        category = HouseholdCategory(home_id=home.id, name="Kitchen")
        session.add(category)
        await session.flush()

        product = Product(name="Oat Milk", barcode="0005555041700")
        session.add(product)
        await session.flush()

        item = InventoryItem(
            home_id=home.id,
            name="Oat Milk",
            household_category_id=category.id,
            product_id=product.id,
        )
        session.add(item)
        await session.flush()
        item_id = item.id

    async with mock_db.begin() as session:
        item = await session.get(InventoryItem, item_id)
        assert item.product is not None
        assert item.product.name == "Oat Milk"
