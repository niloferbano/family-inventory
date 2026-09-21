from datetime import datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas_base.base import BaseApiSchema


class HouseholdCategoryCreate(BaseApiSchema):
    name: str = Field(..., min_length=1, max_length=60)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class HouseholdCategoryRead(BaseApiSchema):
    id: UUID
    home_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
