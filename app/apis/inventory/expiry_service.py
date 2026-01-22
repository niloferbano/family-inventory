from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid5

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.inventory.events import (InventoryItemExpired,
                                       InventoryItemExpiringSoon)
from app.apis.inventory.models import InventoryItem
from app.apis.inventory.repository import InventoryRepository
from app.apis.inventory.types import InventoryAlertType
from app.core.messaging.broker import EventBroker, EventEnvelope

logger = logging.getLogger(__name__)

EVENT_NAMESPACE = UUID("2b6e6d5f-3f7c-4f34-9f6c-7ab8c2d7c4a1")


@dataclass(frozen=True)
class ExpiryAlertBatch:
    expiring_soon: list[InventoryItem]
    expired: list[InventoryItem]


class InventoryExpiryService:
    def __init__(self, session: AsyncSession, broker: EventBroker):
        self.session = session
        self.repo = InventoryRepository(session)
        self.broker = broker

    async def collect_expiry_alerts(
        self,
        *,
        days: int = 7,
        limit: int = 500,
        today: date | None = None,
    ) -> ExpiryAlertBatch:
        today = today or date.today()

        expiring_new = await self.repo.register_expiry_alerts(
            alert_type=InventoryAlertType.EXPIRING_SOON,
            today=today,
            days=days,
        )
        expired_new = await self.repo.register_expiry_alerts(
            alert_type=InventoryAlertType.EXPIRED,
            today=today,
        )

        # If you want to enforce limit at repo-level for register_expiry_alerts,
        # add limit support there too.
        return ExpiryAlertBatch(expiring_soon=expiring_new, expired=expired_new)

    async def publish_expiry_event(
        self,
        *,
        item: InventoryItem,
        alert_type: InventoryAlertType,
        today: date | None = None,
    ) -> None:
        if not item.expiry_date:
            return

        today = today or date.today()

        event_key = (
            f"inventory:{item.home_id}:{item.id}:{alert_type.value}:{today.isoformat()}"
        )
        event_id = uuid5(EVENT_NAMESPACE, event_key)

        if alert_type == InventoryAlertType.EXPIRING_SOON:
            evt = InventoryItemExpiringSoon(
                event_id=event_id,
                home_id=item.home_id,
                item_id=item.id,
                item_name=item.name,
                expiry_date=item.expiry_date,
                days_left=(item.expiry_date - today).days,
            )
            envelope = EventEnvelope(
                topic="inventory.item.expiring_soon",
                key=str(item.id),
                payload=evt.model_dump(mode="json"),
                headers={
                    "source": "inventory",
                    "home_id": str(item.home_id),
                    "event_id": str(event_id),
                },
            )
            await self.broker.publish(envelope)
            return

        if alert_type == InventoryAlertType.EXPIRED:
            evt = InventoryItemExpired(
                event_id=event_id,
                home_id=item.home_id,
                item_id=item.id,
                item_name=item.name,
                expiry_date=item.expiry_date,
            )
            envelope = EventEnvelope(
                topic="inventory.item.expired",
                key=str(item.id),
                payload=evt.model_dump(mode="json"),
                headers={
                    "source": "inventory",
                    "home_id": str(item.home_id),
                    "event_id": str(event_id),
                },
            )
            await self.broker.publish(envelope)
            return

        raise ValueError("invalid alert_type")
