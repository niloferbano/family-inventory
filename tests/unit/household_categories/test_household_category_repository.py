import pytest

from app.apis.homes.models import Home
from app.apis.household_categories.exceptions import HouseholdCategoryNameConflict
from app.apis.household_categories.models import HouseholdCategory
from app.apis.household_categories.repository import HouseholdCategoryRepository


@pytest.mark.asyncio
async def test_household_category_unique_per_home(mock_db):
    async with mock_db.begin() as session:
        home = Home(name="Category Home")
        session.add(home)
        await session.flush()
        home_id = home.id

        repo = HouseholdCategoryRepository(session)
        created = await repo.create(
            HouseholdCategory(home_id=home_id, name="Electronics")
        )
        assert created.name == "Electronics"

    async with mock_db.begin() as session:
        with pytest.raises(HouseholdCategoryNameConflict):
            await HouseholdCategoryRepository(session).create(
                HouseholdCategory(home_id=home_id, name="Electronics")
            )


@pytest.mark.asyncio
async def test_household_category_list_by_home(mock_db):
    async with mock_db.begin() as session:
        home = Home(name="Garden Home")
        session.add(home)
        await session.flush()
        home_id = home.id

        repo = HouseholdCategoryRepository(session)
        await repo.create(HouseholdCategory(home_id=home_id, name="Garden"))
        await repo.create(HouseholdCategory(home_id=home_id, name="Garage"))

    async with mock_db.begin() as session:
        categories = await HouseholdCategoryRepository(session).list_by_home(home_id)
        assert {c.name for c in categories} == {"Garden", "Garage"}
