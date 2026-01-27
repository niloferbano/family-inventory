from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homeuser.repository import HomeUserRepository
from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent)
from app.apis.notifications.types import (DeliveryStatus, NotificationChannel,
                                          NotificationRecipientType)
from app.core.database.base import EventId, HomeId


class NotificationIngestService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.home_user_repo = HomeUserRepository(session)

    async def handle_inventory_event(
        self, *, topic: str, payload: dict, headers: dict
    ) -> None:
        event_id = EventId(UUID(payload["event_id"]))
        home_id = HomeId(UUID(payload["home_id"]))

        async with self.session.begin():  # one message = one transaction

            event = NotificationEvent(
                id=event_id,
                source="inventory",
                event_type=topic,
                subject=self._subject(topic, payload),
                message=self._message(topic, payload),
                recipients={},  # optional snapshot
            )

            # idempotency savepoint (doesn't kill outer tx)
            try:
                async with self.session.begin_nested():
                    self.session.add(event)
                    await self.session.flush()
            except IntegrityError:
                return  # already processed

            members = await self.home_user_repo.list_members_with_users(home_id)

            deliveries: list[NotificationDelivery] = []
            for user, role in members:
                if not getattr(user, "email", None):
                    continue

                deliveries.append(
                    NotificationDelivery(
                        event_id=event.id,
                        channel=NotificationChannel.EMAIL,
                        recipient_type=NotificationRecipientType.EMAIL,
                        recipient=user.email,
                        status=DeliveryStatus.PENDING,
                    )
                )

            if deliveries:
                self.session.add_all(deliveries)
                await self.session.flush()

    def _subject(self, topic: str, payload: dict) -> str:
        name = payload.get("item_name", "Item")
        return (
            f"Expired: {name}"
            if topic == "inventory.item.expired"
            else f"Expiring soon: {name}"
        )

    def _message(self, topic: str, payload: dict) -> str:
        name = payload.get("item_name", "Item")
        expiry = payload.get("expiry_date")
        if topic == "inventory.item.expired":
            return f"'{name}' is expired (expiry_date={expiry})."
        return f"'{name}' is expiring soon (expiry_date={expiry}, days_left={payload.get('days_left')})."
