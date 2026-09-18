from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas_base.base import BaseApiSchema


class HouseholdCategoryCreate(BaseApiSchema):
    name: str = Field(..., min_length=1, max_length=60)


class HouseholdCategoryRead(BaseApiSchema):
    id: UUID
    home_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
