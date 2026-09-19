import pytest

from app.apis.product.models import Product
from app.apis.product.repository import ProductRepository
from app.apis.product.service import ProductLookupService
from app.integrations.product_catalog.exceptions import ProductCatalogUnavailable
from app.integrations.product_catalog.schemas import ProductCandidate


class _RaisingCatalog:
    """A catalog fake that fails the test if it's ever called -- used to
    prove the local repository check short-circuits the provider."""

    async def lookup_by_barcode(self, barcode: str):
        raise AssertionError(
            "catalog must not be called when the product already exists locally"
        )


class _FakeCatalog:
    def __init__(
        self, result: ProductCandidate | None = None, error: Exception | None = None
    ):
        self._result = result
        self._error = error

    async def lookup_by_barcode(self, barcode: str):
        if self._error is not None:
            raise self._error
        return self._result


@pytest.mark.asyncio
async def test_existing_product_short_circuits_before_the_catalog_is_called(mock_db):
    async with mock_db.begin() as session:
        product = await ProductRepository(session).create(
            Product(name="Oat Milk", barcode="0002222041700")
        )
        product_id = product.id

    async with mock_db.begin() as session:
        result = await ProductLookupService(
            ProductRepository(session), _RaisingCatalog()
        ).lookup("0002222041700")

    assert result.source == "local"
    assert result.product is not None
    assert result.product.id == product_id
    assert result.candidate is None


@pytest.mark.asyncio
async def test_catalog_disabled_returns_not_found(mock_db):
    async with mock_db.begin() as session:
        result = await ProductLookupService(
            ProductRepository(session), catalog=None
        ).lookup("0000000000000")
    assert result.source == "not_found"


@pytest.mark.asyncio
async def test_provider_match_is_returned_as_a_candidate_never_persisted(mock_db):
    candidate = ProductCandidate(
        barcode="0003333041700", name="Soap Bar", source="openfoodfacts"
    )
    async with mock_db.begin() as session:
        result = await ProductLookupService(
            ProductRepository(session), _FakeCatalog(result=candidate)
        ).lookup("0003333041700")
    assert result.source == "external"
    assert result.candidate == candidate
    assert result.product is None

    async with mock_db.begin() as session:
        assert await ProductRepository(session).get_by_barcode("0003333041700") is None


@pytest.mark.asyncio
async def test_provider_no_match_is_not_found(mock_db):
    async with mock_db.begin() as session:
        result = await ProductLookupService(
            ProductRepository(session), _FakeCatalog(result=None)
        ).lookup("0004444041700")
    assert result.source == "not_found"


@pytest.mark.asyncio
async def test_provider_failure_degrades_to_provider_unavailable(mock_db):
    async with mock_db.begin() as session:
        result = await ProductLookupService(
            ProductRepository(session),
            _FakeCatalog(error=ProductCatalogUnavailable("openfoodfacts")),
        ).lookup("0005555041700")
    assert result.source == "provider_unavailable"
    assert result.product is None
    assert result.candidate is None
