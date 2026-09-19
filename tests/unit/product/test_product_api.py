import pytest

from app.apis.product.router import get_catalog_client
from app.integrations.product_catalog.exceptions import ProductCatalogUnavailable
from app.integrations.product_catalog.schemas import ProductCandidate
from app.main import app


class _ExplodingCatalog:
    """Fails the test if the provider is ever consulted."""

    async def lookup_by_barcode(self, barcode: str):
        raise AssertionError("provider must not be called for a known barcode")


class _FakeCatalog:
    def __init__(
        self, candidate: ProductCandidate | None = None, error: Exception | None = None
    ):
        self._candidate = candidate
        self._error = error

    async def lookup_by_barcode(self, barcode: str):
        if self._error is not None:
            raise self._error
        return self._candidate


def _override_catalog(client_):
    app.dependency_overrides[get_catalog_client] = lambda: client_


def _clear_catalog_override():
    app.dependency_overrides.pop(get_catalog_client, None)


@pytest.mark.asyncio
async def test_create_and_search_product(client, auth_headers):
    response = await client.post(
        "/products", json={"name": "Milk"}, headers=auth_headers
    )
    assert response.status_code == 201
    product = response.json()
    assert product["id"]
    assert product["name"] == "Milk"
    response = await client.get("/products?q=Milk", headers=auth_headers)
    assert response.status_code == 200
    assert product in response.json()


@pytest.mark.asyncio
async def test_products_require_authentication(client):
    assert (await client.get("/products?q=Milk")).status_code == 401
    assert (await client.post("/products", json={"name": "Milk"})).status_code == 401
    assert (await client.get("/products/lookup/0000000000000")).status_code == 401


@pytest.mark.asyncio
async def test_create_product_with_barcode_is_idempotent(client, auth_headers):
    payload = {"name": "Soap Bar", "barcode": "0003333041700", "brand": "CleanCo"}
    first = await client.post("/products", json=payload, headers=auth_headers)
    assert first.status_code == 201
    first_body = first.json()
    assert first_body["barcode"] == "0003333041700"
    assert first_body["brand"] == "CleanCo"

    second = await client.post(
        "/products",
        json={"name": "Soap Bar (duplicate attempt)", "barcode": "0003333041700"},
        headers=auth_headers,
    )
    assert second.status_code == 201
    second_body = second.json()
    assert second_body["id"] == first_body["id"]
    # The first insert wins; the "duplicate attempt" name never lands.
    assert second_body["name"] == "Soap Bar"


@pytest.mark.asyncio
async def test_lookup_returns_existing_product_without_calling_the_provider(
    client, auth_headers
):
    created = await client.post(
        "/products",
        json={"name": "Oat Milk", "barcode": "0002222041700"},
        headers=auth_headers,
    )
    assert created.status_code == 201

    _override_catalog(_ExplodingCatalog())
    try:
        res = await client.get("/products/lookup/0002222041700", headers=auth_headers)
    finally:
        _clear_catalog_override()

    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "local"
    assert body["product"]["barcode"] == "0002222041700"
    assert body["candidate"] is None


@pytest.mark.asyncio
async def test_lookup_returns_a_candidate_from_the_provider(client, auth_headers):
    candidate = ProductCandidate(
        barcode="0009999041700", name="New Item", source="openfoodfacts"
    )
    _override_catalog(_FakeCatalog(candidate=candidate))
    try:
        res = await client.get("/products/lookup/0009999041700", headers=auth_headers)
    finally:
        _clear_catalog_override()

    assert res.status_code == 200
    body = res.json()
    assert body["source"] == "external"
    assert body["product"] is None
    assert body["candidate"]["name"] == "New Item"
    assert body["candidate"]["source"] == "openfoodfacts"

    # Never auto-persisted.
    search = await client.get(
        "/products", params={"q": "New Item"}, headers=auth_headers
    )
    assert search.json() == []


@pytest.mark.asyncio
async def test_lookup_not_found_returns_404(client, auth_headers):
    _override_catalog(_FakeCatalog(candidate=None))
    try:
        res = await client.get("/products/lookup/0000000000099", headers=auth_headers)
    finally:
        _clear_catalog_override()

    assert res.status_code == 404
    assert res.json()["source"] == "not_found"


@pytest.mark.asyncio
async def test_lookup_provider_failure_returns_200_provider_unavailable(
    client, auth_headers
):
    _override_catalog(_FakeCatalog(error=ProductCatalogUnavailable("openfoodfacts")))
    try:
        res = await client.get("/products/lookup/0000000000088", headers=auth_headers)
    finally:
        _clear_catalog_override()

    assert res.status_code == 200
    assert res.json()["source"] == "provider_unavailable"


@pytest.mark.asyncio
async def test_lookup_disabled_by_default_returns_not_found(client, auth_headers):
    # No override -- exercises the real get_catalog_client dependency with
    # PRODUCT_CATALOG.enabled defaulting to False.
    res = await client.get("/products/lookup/0000000000077", headers=auth_headers)
    assert res.status_code == 404
    assert res.json()["source"] == "not_found"


@pytest.mark.asyncio
async def test_create_product_normalizes_barcode_whitespace(client, auth_headers):
    response = await client.post(
        "/products",
        json={"name": "Padded Barcode", "barcode": "  0001111041700  "},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["barcode"] == "0001111041700"


@pytest.mark.asyncio
async def test_create_product_rejects_non_numeric_barcode(client, auth_headers):
    response = await client.post(
        "/products",
        json={"name": "Bad Barcode", "barcode": "abc123"},
        headers=auth_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_lookup_normalizes_barcode_whitespace(client, auth_headers):
    created = await client.post(
        "/products",
        json={"name": "Oat Milk 2", "barcode": "0004444041700"},
        headers=auth_headers,
    )
    assert created.status_code == 201

    res = await client.get(
        "/products/lookup/%20%200004444041700%20%20", headers=auth_headers
    )
    assert res.status_code == 200
    assert res.json()["source"] == "local"


@pytest.mark.asyncio
async def test_lookup_rejects_non_numeric_barcode(client, auth_headers):
    res = await client.get("/products/lookup/not-a-barcode", headers=auth_headers)
    assert res.status_code == 422
