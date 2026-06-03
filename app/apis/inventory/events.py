from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid5

from pydantic import BaseModel

from app.apis.inventory.models import InventoryItem
from app.apis.inventory.types import InventoryAlertType
from app.apis.notifications.brokers import EventEnvelope
from app.core.database.base import HomeId, InventoryId, NotificationEventId


class InventoryItemExpiringSoon(BaseModel):
    event_id: NotificationEventId
    home_id: HomeId
    item_id: InventoryId
    item_name: str
    expiry_date: date
    days_left: int


class InventoryItemExpired(BaseModel):
    event_id: NotificationEventId
    home_id: HomeId
    item_id: InventoryId
    item_name: str
    expiry_date: date


EVENT_NAMESPACE = UUID("2b6e6d5f-3f7c-4f34-9f6c-7ab8c2d7c4a1")


@dataclass(frozen=True)
class InventoryEventFactory:
    namespace: UUID = EVENT_NAMESPACE

    def expiry_envelope(
        self,
        *,
        item: InventoryItem,
        alert_type: InventoryAlertType,
        today: date,
    ) -> EventEnvelope | None:
        if not item.expiry_date:
            return None

        event_key = (
            f"inventory:{item.home_id}:{item.id}:{alert_type.value}:{today.isoformat()}"
        )
        event_id = NotificationEventId(uuid5(self.namespace, event_key))

        if alert_type == InventoryAlertType.EXPIRING_SOON:
            expiring_evt = InventoryItemExpiringSoon(
                event_id=event_id,
                home_id=item.home_id,
                item_id=item.id,
                item_name=item.name,
                expiry_date=item.expiry_date,
                days_left=(item.expiry_date - today).days,
            )
            return EventEnvelope(
                topic="inventory.item.expiring_soon",
                key=str(item.id),
                payload=expiring_evt.model_dump(mode="json"),
                headers={
                    "source": "inventory",
                    "home_id": str(item.home_id),
                    "event_id": str(event_id),
                },
            )

        if alert_type == InventoryAlertType.EXPIRED:
            expired_evt = InventoryItemExpired(
                event_id=event_id,
                home_id=item.home_id,
                item_id=item.id,
                item_name=item.name,
                expiry_date=item.expiry_date,
            )
            return EventEnvelope(
                topic="inventory.item.expired",
                key=str(item.id),
                payload=expired_evt.model_dump(mode="json"),
                headers={
                    "source": "inventory",
                    "home_id": str(item.home_id),
                    "event_id": str(event_id),
                },
            )

        raise ValueError("invalid alert_type")
