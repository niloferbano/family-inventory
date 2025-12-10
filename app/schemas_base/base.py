from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class BaseApiSchema(BaseModel):
    """Base schema with common Pydantic v2 config."""

    model_config = ConfigDict(
        extra="forbid",  # Forbid extra fields in input
        from_attributes=True,  # Enable ORM mode
    )


T = TypeVar("T")


class PaginatedOutput(BaseModel, Generic[T]):
    total: int = Field(..., description="Total number of records")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")
    results: list[T] = Field(..., description="Paginated results")
