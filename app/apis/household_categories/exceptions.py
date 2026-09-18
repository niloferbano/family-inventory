from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import DomainConflictError


class HouseholdCategoryNameConflict(DomainConflictError):
    def __init__(self, name: str):
        super().__init__(
            code=ErrorCode.HOUSEHOLD_CATEGORY_NAME_CONFLICT,
            message="A category with this name already exists in this home.",
            details={"name": name},
        )
