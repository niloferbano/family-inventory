from app.apis.errors.errors import ErrorResponse

ConflictResponse = {
    "model": ErrorResponse,
    "description": "Conflict / duplicate resource",
}

ForbiddenResponse = {
    "model": ErrorResponse,
    "description": "Permission denied",
}

NotFoundResponse = {
    "model": ErrorResponse,
    "description": "Resource not found",
}

UnauthorizedResponse = {
    "model": ErrorResponse,
    "description": "Authentication required",
}
