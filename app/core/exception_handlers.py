from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.database.exceptions import (DomainConflictError,
                                          DomainNotFoundError,
                                          DomainPermissionError)


def register_exception_handlers(app: FastAPI) -> None:

    @app.exception_handler(DomainConflictError)
    async def handle_domain_conflict(
        request: Request,
        exc: DomainConflictError,
    ):
        return JSONResponse(
            status_code=getattr(exc, "status_code", 409),
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(DomainPermissionError)
    async def handle_permission(
        request: Request,
        exc: DomainPermissionError,
    ):
        return JSONResponse(
            status_code=403,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

    @app.exception_handler(DomainNotFoundError)
    async def handle_not_found(
        request: Request,
        exc: DomainNotFoundError,
    ):
        return JSONResponse(
            status_code=404,
            content={
                "error": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
