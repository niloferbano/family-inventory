import pytest

from app.apis.product.models import Product
from app.apis.product.repository import ProductRepository


@pytest.mark.asyncio
async def test_create_and_get_by_id(mock_db):
    async with mock_db.begin() as session:
        product = await ProductRepository(session).create(
            Product(
                name="Whole Milk",
                barcode="0001111041700",
                brand="Acme",
                image_url="https://example.com/milk.jpg",
            )
        )
        product_id = product.id

    async with mock_db.begin() as session:
        found = await ProductRepository(session).get_by_id(product_id)
        assert found is not None
        assert found.name == "Whole Milk"
        assert found.brand == "Acme"
        assert found.image_url == "https://example.com/milk.jpg"
        assert found.is_active is True


@pytest.mark.asyncio
async def test_get_by_barcode(mock_db):
    async with mock_db.begin() as session:
        await ProductRepository(session).create(
            Product(name="Oat Milk", barcode="0002222041700")
        )

    async with mock_db.begin() as session:
        found = await ProductRepository(session).get_by_barcode("0002222041700")
        assert found is not None
        assert found.name == "Oat Milk"

        missing = await ProductRepository(session).get_by_barcode("does-not-exist")
        assert missing is None


@pytest.mark.asyncio
async def test_find_or_create_by_barcode_is_idempotent(mock_db):
    async with mock_db.begin() as session:
        first, first_created = await ProductRepository(
            session
        ).find_or_create_by_barcode(
            barcode="0003333041700", name="Soap Bar", brand="CleanCo"
        )
        assert first_created is True
        first_id = first.id

    async with mock_db.begin() as session:
        second, second_created = await ProductRepository(
            session
        ).find_or_create_by_barcode(
            barcode="0003333041700", name="Soap Bar (duplicate attempt)"
        )
        assert second_created is False
        assert second.id == first_id
        # The first insert wins; the "duplicate attempt" name never lands.
        assert second.name == "Soap Bar"


@pytest.mark.asyncio
async def test_search_by_name_excludes_inactive_by_default(mock_db):
    async with mock_db.begin() as session:
        repo = ProductRepository(session)
        active = await repo.create(Product(name="Almond Milk"))
        inactive = await repo.create(Product(name="Almond Milk Classic"))
        await repo.deactivate(inactive)

    async with mock_db.begin() as session:
        results = await ProductRepository(session).search_by_name("almond")
        names = {p.name for p in results}
        assert active.name in names
        assert inactive.name not in names

        results_with_inactive = await ProductRepository(session).search_by_name(
            "almond", include_inactive=True
        )
        assert {p.name for p in results_with_inactive} == {
            active.name,
            inactive.name,
        }


@pytest.mark.asyncio
async def test_deactivate_hides_product_from_default_lookups(mock_db):
    async with mock_db.begin() as session:
        repo = ProductRepository(session)
        product = await repo.create(
            Product(name="Discontinued Snack", barcode="0004444041700")
        )
        product_id = product.id
        await repo.deactivate(product)

    async with mock_db.begin() as session:
        repo = ProductRepository(session)
        assert await repo.get_by_id(product_id) is None
        assert await repo.get_by_id(product_id, include_inactive=True) is not None
        assert await repo.get_by_barcode("0004444041700") is None
        assert (
            await repo.get_by_barcode("0004444041700", include_inactive=True)
            is not None
        )


@pytest.mark.asyncio
async def test_reactivate_restores_default_visibility(mock_db):
    async with mock_db.begin() as session:
        repo = ProductRepository(session)
        product = await repo.create(Product(name="Seasonal Item"))
        product_id = product.id
        await repo.deactivate(product)

    async with mock_db.begin() as session:
        repo = ProductRepository(session)
        product = await repo.get_by_id(product_id, include_inactive=True)
        await repo.reactivate(product)

    async with mock_db.begin() as session:
        found = await ProductRepository(session).get_by_id(product_id)
        assert found is not None
        assert found.is_active is True
