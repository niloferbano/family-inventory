from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import DomainConflictError, DomainNotFoundError


class ProductBarcodeConflict(DomainConflictError):
    def __init__(self, barcode: str):
        super().__init__(
            code=ErrorCode.PRODUCT_BARCODE_CONFLICT,
            message="A product with this barcode already exists.",
            details={"barcode": barcode},
        )


class ProductNotFound(DomainNotFoundError):
    def __init__(self, product_id: str):
        super().__init__(
            code=ErrorCode.PRODUCT_NOT_FOUND,
            message="Product not found.",
            details={"product_id": product_id},
        )
