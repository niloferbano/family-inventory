from pydantic import BaseModel, ConfigDict


class BaseApiSchema(BaseModel):
    """Base schema with common Pydantic v2 config."""

    model_config = ConfigDict(
        extra="forbid",  # Forbid extra fields in input
        from_attributes=True,  # Enable ORM mode
    )
