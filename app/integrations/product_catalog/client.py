from typing import Protocol

from app.integrations.product_catalog.schemas import ProductCandidate


class ProductCatalogClient(Protocol):
    """Abstraction over a third-party product catalog provider (issue #50).

    A Protocol (not an ABC): a new provider or a test fake needs no
    inheritance, just this shape.
    """

    async def lookup_by_barcode(self, barcode: str) -> ProductCandidate | None:
        """Return a candidate for this barcode, or None if the provider has
        no match.

        Raises ProductCatalogUnavailable (see exceptions.py) for anything
        that means "couldn't ask" -- never returns a half-populated
        candidate.
        """
        ...
