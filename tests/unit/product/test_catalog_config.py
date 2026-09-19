import pytest
import pytest_asyncio

from app.apis.product import router as product_router
from app.apis.product.router import close_catalog_client, get_catalog_client
from app.core.configs.config import settings
from app.core.configs.product_catalog_config import ProductCatalogSettings
from app.integrations.product_catalog.open_food_facts import OpenFoodFactsClient


@pytest_asyncio.fixture(autouse=True)
async def _reset_catalog_client():
    # get_catalog_client() is a lazily-created module-level singleton (issue
    # #50 review: avoid leaking a fresh httpx.AsyncClient per request), so
    # tests must close/clear it themselves rather than relying on a
    # request-scoped teardown.
    yield
    await close_catalog_client()


def test_catalog_disabled_by_default():
    # Test the declared default, not settings overridden by the local .env.
    assert ProductCatalogSettings().enabled is False


def test_get_catalog_client_returns_none_when_disabled(monkeypatch):
    monkeypatch.setattr(settings.PRODUCT_CATALOG, "enabled", False)
    assert get_catalog_client() is None


def test_get_catalog_client_returns_a_client_when_enabled(monkeypatch):
    monkeypatch.setattr(settings.PRODUCT_CATALOG, "enabled", True)
    client = get_catalog_client()
    assert isinstance(client, OpenFoodFactsClient)


def test_get_catalog_client_reuses_the_same_instance(monkeypatch):
    # The whole point of the fix: no new client (and no new underlying
    # httpx.AsyncClient) per call.
    monkeypatch.setattr(settings.PRODUCT_CATALOG, "enabled", True)
    first = get_catalog_client()
    second = get_catalog_client()
    assert first is second


@pytest.mark.asyncio
async def test_close_catalog_client_clears_the_singleton(monkeypatch):
    monkeypatch.setattr(settings.PRODUCT_CATALOG, "enabled", True)
    client = get_catalog_client()
    assert product_router._catalog_client is client

    await close_catalog_client()

    assert product_router._catalog_client is None
    # A later call creates a fresh instance rather than reusing the closed one.
    assert get_catalog_client() is not client


@pytest.mark.asyncio
async def test_close_catalog_client_is_a_no_op_when_never_created():
    # Shouldn't raise just because the feature was never enabled.
    await close_catalog_client()
