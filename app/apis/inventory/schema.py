from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.apis.inventory.models import InventoryCategory
from app.schemas_base.base import BaseApiSchema, PaginatedOutput


class InventoryCreateRequest(BaseModel):
    name: str
    category: InventoryCategory
    quantity: int = 1
    unit: str = "pcs"
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
    home_id: UUID


class InventoryGetResponse(BaseApiSchema):
    id: UUID
    name: str
    category: InventoryCategory
    quantity: int
    unit: str
    expiry_date: date | None
    notes: str | None
    home_id: UUID


class PaginatedInventorytItemResponse(PaginatedOutput[InventoryGetResponse]):
    results: list[InventoryGetResponse]
