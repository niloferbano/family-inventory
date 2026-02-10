from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.apis.inventory.types import InventoryCategory
from app.core.database.base import HomeId
from app.schemas_base.base import BaseApiSchema, PaginatedOutput


class InventoryCreateRequest(BaseModel):
    name: str
    category: InventoryCategory
    quantity: int = 1
    unit: str = "pcs"
    expiry_date: date | None = None
    notes: str | None = None


class InventoryUpdateRequest(BaseModel):
    name: str | None = None
    category: InventoryCategory | None = None
    quantity: int | None = None
    unit: str | None = None
    expiry_date: date | None = None
    notes: str | None = None


class InventoryCreateResponse(BaseApiSchema):
    id: UUID
    name: str
    category: InventoryCategory
    quantity: int
    unit: str
    expiry_date: date | None
    notes: str | None
    home_id: HomeId


class InventoryGetResponse(BaseApiSchema):
    id: UUID
    name: str
    category: InventoryCategory
    quantity: int
    unit: str
    expiry_date: date | None
    notes: str | None
    home_id: HomeId


class PaginatedInventoryItemResponse(PaginatedOutput[InventoryGetResponse]):
    results: list[InventoryGetResponse]


class ExpiryFilter(StrEnum):
    EXPIRED = "expired"
    EXPIRING_SOON = "expiring_soon"


class InventoryFilters(BaseApiSchema):
    category: list[InventoryCategory] | None = None
    expiry: ExpiryFilter | None = None
    days: int = Field(default=7, ge=1, le=365)

    @model_validator(mode="after")
    def validate_days_usage(self):
        if self.expiry != ExpiryFilter.EXPIRING_SOON:
            self.days = 7
        return self
