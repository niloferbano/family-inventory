from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.core.database.base import HomeId, InventoryId


class InventoryItemExpiringSoon(BaseModel):
    event_id: UUID
    home_id: HomeId
    item_id: InventoryId
    item_name: str
    expiry_date: date
    days_left: int


class InventoryItemExpired(BaseModel):
    event_id: UUID
    home_id: HomeId
    item_id: InventoryId
    item_name: str
    expiry_date: date
