from pydantic import BaseModel


class ProductCatalogSettings(BaseModel):
    """External product catalog lookup (issue #50).

    Off by default: existing manual-entry behavior (POST /products with
    just a name) is completely unchanged until an operator opts in per
    environment.
    """

    enabled: bool = False
    provider: str = "openfoodfacts"
    base_url: str = "https://world.openfoodfacts.org"
    timeout_seconds: float = 3.0
