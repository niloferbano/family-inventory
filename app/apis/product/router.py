import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AfterValidator, BaseModel, Field, field_validator

from app.apis.product.models import Product
from app.apis.product.repository import ProductRepository
from app.apis.product.service import LookupSource, ProductLookupService
from app.core.configs.config import settings
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user
from app.integrations.product_catalog.client import ProductCatalogClient
from app.integrations.product_catalog.open_food_facts import OpenFoodFactsClient
from app.integrations.product_catalog.schemas import ProductCandidate
from app.schemas_base.base import BaseApiSchema

_BARCODE_PATTERN = re.compile(r"^\d+$")


def _normalize_barcode(value: str) -> str:
    """Strip incidental whitespace and require digits only.

    Deliberately doesn't pin an exact length: real-world barcodes are
    GTIN-8/12/13/14 (and Open Food Facts accepts other digit-string lengths
    too) -- constraining to one length would reject otherwise-valid codes.
    """
    normalized = value.strip()
    if not _BARCODE_PATTERN.fullmatch(normalized):
        raise ValueError("barcode must contain only digits")
    return normalized


router = APIRouter(
    prefix="/products", tags=["Products"], dependencies=[Depends(get_current_user)]
)


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    barcode: str | None = Field(default=None, max_length=64)
    brand: str | None = Field(default=None, max_length=100)
    external_category: str | None = Field(default=None, max_length=100)
    image_url: str | None = Field(default=None, max_length=500)

    @field_validator("barcode")
    @classmethod
    def _validate_barcode(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_barcode(value)


class ProductRead(BaseApiSchema):
    id: UUID
    name: str
    barcode: str | None = None
    brand: str | None = None
    external_category: str | None = None
    image_url: str | None = None


class ProductLookupResponse(BaseModel):
    source: LookupSource
    product: ProductRead | None = None
    candidate: ProductCandidate | None = None


_catalog_client: OpenFoodFactsClient | None = None


def get_catalog_client() -> ProductCatalogClient | None:
    """Feature-flagged: returns None (catalog lookups skipped entirely)
    unless PRODUCT_CATALOG.enabled is set (issue #50).

    Lazily creates and reuses a single OpenFoodFactsClient (and the
    httpx.AsyncClient it owns) for the process's lifetime rather than one
    per request, so connections are pooled instead of leaked. Paired with
    close_catalog_client(), which app.main's lifespan calls on shutdown.

    A module-level singleton rather than something stashed on app.state:
    the test suite's client fixture never runs FastAPI's lifespan (no
    LifespanManager), so a resource that only existed on app.state after
    lifespan startup would be unreachable from tests that enable the
    feature flag directly.
    """
    global _catalog_client
    if not settings.PRODUCT_CATALOG.enabled:
        return None
    if _catalog_client is None:
        _catalog_client = OpenFoodFactsClient(
            base_url=settings.PRODUCT_CATALOG.base_url,
            timeout_seconds=settings.PRODUCT_CATALOG.timeout_seconds,
        )
    return _catalog_client


async def close_catalog_client() -> None:
    """Close the shared catalog client's underlying httpx.AsyncClient, if
    one was ever created. Called from app.main's lifespan shutdown."""
    global _catalog_client
    if _catalog_client is not None:
        await _catalog_client.aclose()
        _catalog_client = None


@router.get("", response_model=list[ProductRead])
async def search_products(
    q: str = Query(min_length=1, max_length=100), db_manager=Depends(get_db)
):
    async with db_manager.begin() as session:
        return await ProductRepository(session).search_by_name(q)


@router.get("/lookup/{barcode}", response_model=ProductLookupResponse)
async def lookup_product(
    barcode: Annotated[str, AfterValidator(_normalize_barcode)],
    response: Response,
    db_manager=Depends(get_db),
    catalog: ProductCatalogClient | None = Depends(get_catalog_client),
):
    """Look up a product by barcode: the local catalog first, then the
    external provider (if enabled) only when we don't already have it.

    Never auto-persists a provider match -- POST /products, separately,
    saves a reviewed candidate. A provider failure returns 200 with
    source="provider_unavailable", never a 5xx: it's an expected, handled
    outcome for the caller (typically falling back to manual entry), not a
    server error.
    """
    async with db_manager.begin() as session:
        result = await ProductLookupService(ProductRepository(session), catalog).lookup(
            barcode
        )

    if result.source == "not_found":
        response.status_code = 404

    return ProductLookupResponse(
        source=result.source,
        product=ProductRead.model_validate(result.product) if result.product else None,
        candidate=result.candidate,
    )


@router.post("", response_model=ProductRead, status_code=201)
async def create_product(payload: ProductCreate, db_manager=Depends(get_db)):
    async with db_manager.begin() as session:
        repo = ProductRepository(session)
        if payload.barcode:
            # Idempotent: a race on the same barcode resolves to the same
            # row rather than a conflict (see
            # ProductRepository.find_or_create_by_barcode).
            product, _created = await repo.find_or_create_by_barcode(
                barcode=payload.barcode,
                name=payload.name,
                brand=payload.brand,
                external_category=payload.external_category,
                image_url=payload.image_url,
            )
            return product
        return await repo.create(Product(name=payload.name))
