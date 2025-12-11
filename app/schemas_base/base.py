from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from app.core.database.pagination import GenericT


class BaseApiSchema(BaseModel):
    """Base schema with common Pydantic v2 config."""

    model_config = ConfigDict(
        extra="forbid",  # Forbid extra fields in input
        from_attributes=True,  # Enable ORM mode
    )


T = TypeVar("T")


class PaginatedOutput(BaseModel, Generic[GenericT]):
    count: int
    total_pages: int
    next: str | None
    previous: str | None
    results: list[GenericT]
