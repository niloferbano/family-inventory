from pydantic import BaseModel


class ProductCandidate(BaseModel):
    """A not-yet-persisted product suggestion from an external catalog
    (issue #50).

    Shaped like Product minus id/is_active/timestamps: a candidate is not a
    row yet. The caller reviews it and explicitly saves it via
    POST /products -- nothing here writes to the database.
    """

    barcode: str
    name: str
    brand: str | None = None
    external_category: str | None = None
    image_url: str | None = None
    source: str  # provider name, e.g. "openfoodfacts" -- audit/display only
