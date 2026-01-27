from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import DomainPermissionError


class AuthenticationRequired(DomainPermissionError):
    def __init__(self):
        super().__init__(
            code=ErrorCode.AUTH_REQUIRED,
            message="Authentication required",
            details={},
        )
