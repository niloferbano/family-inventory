class ProductCatalogUnavailable(Exception):
    """Raised when a third-party product catalog provider could not be
    asked, or its response couldn't be trusted (timeout, non-2xx,
    malformed/invalid payload).

    Never raised for a legitimate "no match" -- that case returns None.
    Caught at the ProductLookupService boundary and never propagated as an
    HTTP error: a provider outage must not look like or affect manual
    product creation (issue #50).
    """

    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"Product catalog provider '{provider}' unavailable")
