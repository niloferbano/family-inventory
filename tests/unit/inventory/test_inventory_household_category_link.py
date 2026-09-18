import pytest
from sqlalchemy.exc import IntegrityError

from app.apis.homes.models import Home
from app.apis.household_categories.models import HouseholdCategory
from app.apis.inventory.models import InventoryItem


@pytest.mark.asyncio
async def test_household_category_is_required(mock_db):
    with pytest.raises(IntegrityError):
        async with mock_db.begin() as session:
            home = Home(name="Missing Category Home")
            session.add(home)
            await session.flush()

            item = InventoryItem(home_id=home.id, name="Milk")
            session.add(item)
            await session.flush()


@pytest.mark.asyncio
async def test_item_links_to_household_category(mock_db):
    async with mock_db.begin() as session:
        home = Home(name="Electronics Home")
        session.add(home)
        await session.flush()

        category = HouseholdCategory(home_id=home.id, name="Electronics")
        session.add(category)
        await session.flush()

        item = InventoryItem(
            home_id=home.id,
            name="Soldering Iron",
            household_category_id=category.id,
        )
        session.add(item)
        await session.flush()
        item_id = item.id

    async with mock_db.begin() as session:
        item = await session.get(InventoryItem, item_id)
        assert item.household_category is not None
        assert item.household_category.name == "Electronics"


@pytest.mark.asyncio
async def test_deleting_referenced_household_category_is_blocked(mock_db):
    async with mock_db.begin() as session:
        home = Home(name="Garden Home")
        session.add(home)
        await session.flush()

        category = HouseholdCategory(home_id=home.id, name="Garden")
        session.add(category)
        await session.flush()
        category_id = category.id

        item = InventoryItem(
            home_id=home.id,
            name="Rake",
            household_category_id=category_id,
        )
        session.add(item)
        await session.flush()

    with pytest.raises(IntegrityError):
        async with mock_db.begin() as session:
            category = await session.get(HouseholdCategory, category_id)
            await session.delete(category)
            await session.flush()
