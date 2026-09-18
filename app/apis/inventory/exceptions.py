from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import (
    DomainConflictError,
    DomainNotFoundError,
    DomainPermissionError,
)


class InventoryAccessDenied(DomainPermissionError):
    def __init__(self, home_id: str):
        super().__init__(
            code=ErrorCode.INVENTORY_ACCESS_DENIED,
            message="You are not allowed to access this inventory.",
            details={"home_id": home_id},
        )


class InventoryItemNotFound(DomainNotFoundError):
    def __init__(self, item_id: str):
        super().__init__(
            code=ErrorCode.INVENTORY_ITEM_NOT_FOUND,
            message="Inventory item not found.",
            details={"item_id": item_id},
        )


class InventoryCategoryInvalid(DomainConflictError):
    status_code = 422

    def __init__(self):
        super().__init__(
            code=ErrorCode.INVENTORY_CATEGORY_INVALID,
            message="Select a category belonging to this home.",
        )
