# app/core/database/exceptions.py
from typing import Any

from app.core.database.error_codes import ErrorCode


class DomainError(Exception):
    status_code: int = 400

    def __init__(
        self,
        *,
        code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
    ):
        if not isinstance(code, ErrorCode):
            raise TypeError("code must be an ErrorCode enum")
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)


class DomainPermissionError(DomainError):
    status_code = 403


class DomainNotFoundError(DomainError):
    status_code = 404


class DomainConflictError(DomainError):
    status_code = 409
