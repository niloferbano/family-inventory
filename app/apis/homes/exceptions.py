from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import (DomainConflictError,
                                          DomainNotFoundError)


class HomeAlreadyExists(DomainConflictError):
    def __init__(self, home_name: str):
        super().__init__(
            code=ErrorCode.HOME_ALREADY_EXISTS,
            message="Home with this name already exists",
            details={"name": home_name},
        )


class HomeNotFound(DomainNotFoundError):
    def __init__(self, home_id):
        super().__init__(
            code=ErrorCode.HOME_NOT_FOUND,
            message="Home not found",
            details={"home_id": str(home_id)},
        )
