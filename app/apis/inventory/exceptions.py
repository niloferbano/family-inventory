# app/apis/inventory/exceptions.py
from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import DomainConflictError


class InventoryItemNameConflict(DomainConflictError):
    def __init__(self, names: list[str]):
        super().__init__(
            code=ErrorCode.INVENTORY_ITEM_NAME_CONFLICT,
            message="One or more inventory items already exist in this home",
            details={"names": names},
        )


class InventoryAccessDenied(DomainConflictError):
    def __init__(self, home_id: str):
        super().__init__(
            code=ErrorCode.INVENTORY_ACCESS_DENIED,
            message="You are not allowed to access this inventory.",
            details={"home_id": home_id},
        )
