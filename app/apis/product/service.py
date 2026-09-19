from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.apis.product.models import Product
from app.apis.product.repository import ProductRepository
from app.integrations.product_catalog.client import ProductCatalogClient
from app.integrations.product_catalog.exceptions import ProductCatalogUnavailable
from app.integrations.product_catalog.schemas import ProductCandidate

LookupSource = Literal["local", "external", "not_found", "provider_unavailable"]


@dataclass(frozen=True)
class ProductLookupResult:
    source: LookupSource
    product: Product | None = None
    candidate: ProductCandidate | None = None


class ProductLookupService:
    """Orchestrates the barcode lookup flow (issue #50).

    The local catalog always wins: the external provider is never consulted
    for a barcode already on file. A provider failure degrades to
    ``provider_unavailable`` rather than raising -- it must never look like,
    or actually cause, a failure to create a product manually.
    """

    def __init__(self, repo: ProductRepository, catalog: ProductCatalogClient | None):
        self._repo = repo
        self._catalog = catalog

    async def lookup(self, barcode: str) -> ProductLookupResult:
        existing = await self._repo.get_by_barcode(barcode)
        if existing is not None:
            return ProductLookupResult(source="local", product=existing)

        if self._catalog is None:
            return ProductLookupResult(source="not_found")

        try:
            candidate = await self._catalog.lookup_by_barcode(barcode)
        except ProductCatalogUnavailable:
            return ProductLookupResult(source="provider_unavailable")

        if candidate is None:
            return ProductLookupResult(source="not_found")

        return ProductLookupResult(source="external", candidate=candidate)
