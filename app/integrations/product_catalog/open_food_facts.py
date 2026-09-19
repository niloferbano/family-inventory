from __future__ import annotations

import httpx
from pydantic import BaseModel, ValidationError

from app.integrations.product_catalog.exceptions import ProductCatalogUnavailable
from app.integrations.product_catalog.schemas import ProductCandidate

PROVIDER_NAME = "openfoodfacts"

# Only the fields this integration actually reads. Keeps the response small
# and this client resilient to unrelated schema growth elsewhere in Open
# Food Facts's v3 API (nutrition, knowledge panels, quality tags, etc).
# See docs/api/ref/api-v3.yaml's "fields" query parameter.
_REQUESTED_FIELDS = "product_name,brands,categories,selected_images"

# v3 nests image URLs as selected_images.<type>.<lang-or-"best">.<pixel
# size> -- there is no flat "image_url" field like v2 had. See
# docs/api/ref/schemas/product_images_v3.yaml.
_IMAGE_TYPE = "front"
_IMAGE_SIZES_BY_PREFERENCE = ("400", "200", "100")

# v3's own not-found/failure signals, from docs/api/ref/responses/
# response-status/response_status.yaml's "status" enum. A 200 response can
# still report "failure"/"success_with_errors" -- unlike v2, which only
# ever used HTTP 200 and an in-body 0/1 status integer, v3 uses a real
# HTTP 404 for "no product with this barcode" (handled separately below)
# and reserves this string enum for request-level problems on an
# otherwise-200 response.
_UNTRUSTWORTHY_STATUSES = {"failure", "success_with_errors"}


class _OpenFoodFactsProduct(BaseModel):
    """Raw shape of the fields this integration reads from Open Food
    Facts's v3 product response. Everything else in their payload is
    ignored."""

    product_name: str | None = None
    brands: str | None = None
    categories: str | None = None
    selected_images: dict | None = None


def _extract_front_image_url(selected_images: dict | None) -> str | None:
    """Best-effort pick of a front-image URL out of v3's
    ``selected_images.<type>.<lang-or-"best">.<pixel size>`` structure
    (a plain dict here -- see the module docstring notes above; not worth
    a dedicated nested Pydantic model for a single optional display field).
    """
    if not isinstance(selected_images, dict):
        return None
    by_language = selected_images.get(_IMAGE_TYPE)
    if not isinstance(by_language, dict):
        return None
    # Prefer Open Food Facts's own "best available" pick; fall back to
    # whatever language entry happens to be present otherwise.
    for sizes in [by_language.get("best"), *by_language.values()]:
        if not isinstance(sizes, dict):
            continue
        for size in _IMAGE_SIZES_BY_PREFERENCE:
            url = sizes.get(size)
            if url:
                return url
    return None


class OpenFoodFactsClient:
    """ProductCatalogClient implementation backed by the public Open Food
    Facts v3 API (issue #50). No API key required.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float,
        http_client: httpx.AsyncClient | None = None,
    ):
        self._client = http_client or httpx.AsyncClient(
            base_url=base_url, timeout=timeout_seconds
        )
        # Only close a client we created ourselves -- a caller-supplied one
        # (tests, or a shared client) is theirs to manage.
        self._owns_client = http_client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def lookup_by_barcode(self, barcode: str) -> ProductCandidate | None:
        try:
            # No ".json" suffix in v3 (unlike v2's
            # /api/v2/product/{barcode}.json) -- JSON is the endpoint's
            # only representation.
            response = await self._client.get(
                f"/api/v3/product/{barcode}",
                params={"fields": _REQUESTED_FIELDS},
            )
        except httpx.HTTPError as exc:
            raise ProductCatalogUnavailable(PROVIDER_NAME) from exc

        if response.status_code == 404:
            # v3's own "no product with this barcode" signal -- a real
            # answer, not a failure to ask.
            return None
        if response.status_code != 200:
            # Includes the 302 cross-project redirect (e.g. a barcode that
            # turns out to belong to Open Beauty Facts, not Open Food
            # Facts): not a product we can use, and not worth following
            # into another provider's API for this integration.
            raise ProductCatalogUnavailable(PROVIDER_NAME)

        try:
            body = response.json()
        except ValueError as exc:
            raise ProductCatalogUnavailable(PROVIDER_NAME) from exc

        if not isinstance(body, dict):
            raise ProductCatalogUnavailable(PROVIDER_NAME)
        if body.get("status") in _UNTRUSTWORTHY_STATUSES:
            raise ProductCatalogUnavailable(PROVIDER_NAME)

        try:
            raw = _OpenFoodFactsProduct.model_validate(body.get("product") or {})
        except ValidationError as exc:
            raise ProductCatalogUnavailable(PROVIDER_NAME) from exc

        if not raw.product_name:
            # Has the barcode but no usable name -- treat as no match.
            return None

        return ProductCandidate(
            barcode=barcode,
            name=raw.product_name,
            brand=raw.brands,
            external_category=raw.categories,
            image_url=_extract_front_image_url(raw.selected_images),
            source=PROVIDER_NAME,
        )
