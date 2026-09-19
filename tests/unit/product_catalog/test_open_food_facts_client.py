import httpx
import pytest

from app.integrations.product_catalog.exceptions import ProductCatalogUnavailable
from app.integrations.product_catalog.open_food_facts import OpenFoodFactsClient


def _client(handler) -> OpenFoodFactsClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(
        transport=transport, base_url="https://world.openfoodfacts.org"
    )
    return OpenFoodFactsClient(
        base_url="https://world.openfoodfacts.org",
        timeout_seconds=3.0,
        http_client=http_client,
    )


@pytest.mark.asyncio
async def test_lookup_requests_the_v3_endpoint_with_no_json_suffix():
    def handler(request: httpx.Request) -> httpx.Response:
        # v3 has no ".json" suffix (unlike v2's
        # /api/v2/product/{barcode}.json) and only the fields we asked for.
        assert request.url.path == "/api/v3/product/0001111041700"
        assert (
            request.url.params["fields"]
            == "product_name,brands,categories,selected_images"
        )
        return httpx.Response(200, json={"status": "success", "product": {}})

    await _client(handler).lookup_by_barcode("0001111041700")


@pytest.mark.asyncio
async def test_lookup_maps_a_real_match_including_the_nested_front_image():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "product": {
                    "product_name": "Whole Milk",
                    "brands": "Acme",
                    "categories": "Dairy",
                    "selected_images": {
                        "front": {
                            "best": {
                                "400": "https://images.example/milk-400.jpg",
                                "100": "https://images.example/milk-100.jpg",
                            },
                            "en": {"400": "https://images.example/milk-en-400.jpg"},
                        },
                        "ingredients": {
                            "en": {"400": "https://images.example/ingredients.jpg"}
                        },
                    },
                },
            },
        )

    candidate = await _client(handler).lookup_by_barcode("0001111041700")
    assert candidate is not None
    assert candidate.barcode == "0001111041700"
    assert candidate.name == "Whole Milk"
    assert candidate.brand == "Acme"
    assert candidate.external_category == "Dairy"
    # Prefers "best", and the largest available size.
    assert candidate.image_url == "https://images.example/milk-400.jpg"
    assert candidate.source == "openfoodfacts"


@pytest.mark.asyncio
async def test_lookup_falls_back_to_any_language_when_best_is_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "product": {
                    "product_name": "Oat Milk",
                    "selected_images": {
                        "front": {
                            "fr": {"200": "https://images.example/oat-fr-200.jpg"}
                        }
                    },
                },
            },
        )

    candidate = await _client(handler).lookup_by_barcode("0002222041700")
    assert candidate is not None
    assert candidate.image_url == "https://images.example/oat-fr-200.jpg"


@pytest.mark.asyncio
async def test_lookup_image_url_is_none_when_no_images_present():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "success", "product": {"product_name": "Plain Item"}}
        )

    candidate = await _client(handler).lookup_by_barcode("0003333041700")
    assert candidate is not None
    assert candidate.image_url is None


@pytest.mark.asyncio
async def test_lookup_returns_none_on_http_404():
    # v3 signals "no product with this barcode" as a real 404, unlike v2's
    # 200 + in-body status:0.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    assert await _client(handler).lookup_by_barcode("0000000000000") is None


@pytest.mark.asyncio
async def test_lookup_returns_none_when_product_has_no_usable_name():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"status": "success", "product": {"brands": "Acme"}}
        )

    assert await _client(handler).lookup_by_barcode("0000000000001") is None


@pytest.mark.asyncio
async def test_lookup_raises_when_status_is_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "failure", "product": {"product_name": "Untrusted"}},
        )

    with pytest.raises(ProductCatalogUnavailable):
        await _client(handler).lookup_by_barcode("0000000000006")


@pytest.mark.asyncio
async def test_lookup_raises_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    with pytest.raises(ProductCatalogUnavailable):
        await _client(handler).lookup_by_barcode("0000000000002")


@pytest.mark.asyncio
async def test_lookup_raises_on_unexpected_status_code():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(ProductCatalogUnavailable):
        await _client(handler).lookup_by_barcode("0000000000003")


@pytest.mark.asyncio
async def test_lookup_raises_on_cross_project_redirect():
    # A 302 to another Open ... Facts project (e.g. Open Beauty Facts) --
    # not a product this integration can use, and not followed.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={
                "Location": "https://world.openbeautyfacts.org/api/v3/product/0000000000007"
            },
        )

    with pytest.raises(ProductCatalogUnavailable):
        await _client(handler).lookup_by_barcode("0000000000007")


@pytest.mark.asyncio
async def test_lookup_raises_on_malformed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    with pytest.raises(ProductCatalogUnavailable):
        await _client(handler).lookup_by_barcode("0000000000004")


@pytest.mark.asyncio
async def test_lookup_raises_on_invalid_payload_shape():
    def handler(request: httpx.Request) -> httpx.Response:
        # "product" is a list, not an object -- fails validation.
        return httpx.Response(200, json={"status": "success", "product": ["nope"]})

    with pytest.raises(ProductCatalogUnavailable):
        await _client(handler).lookup_by_barcode("0000000000005")
