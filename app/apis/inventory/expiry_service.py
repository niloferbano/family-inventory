from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.inventory.events import InventoryEventFactory
from app.apis.inventory.models import InventoryItem
from app.apis.inventory.repository import InventoryRepository
from app.apis.inventory.types import InventoryAlertType
from app.apis.notifications.brokers import EventBroker

logger = logging.getLogger(__name__)

EVENT_NAMESPACE = UUID("2b6e6d5f-3f7c-4f34-9f6c-7ab8c2d7c4a1")


@dataclass(frozen=True)
class ExpiryAlertBatch:
    expiring_soon: list[InventoryItem]
    expired: list[InventoryItem]


class InventoryExpiryService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        broker: EventBroker,
        factory: InventoryEventFactory | None = None,
    ):
        self.session = session
        self.repo = InventoryRepository(session)
        self.broker = broker
        self.factory = factory or InventoryEventFactory()

    async def publish_expiry_event(
        self,
        *,
        item: InventoryItem,
        alert_type: InventoryAlertType,
        today: date | None = None,
    ) -> None:
        today = today or date.today()

        envelope = self.factory.expiry_envelope(
            item=item,
            alert_type=alert_type,
            today=today,
        )
        if envelope is None:
            return

        await self.broker.publish(envelope)
