from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent)
from app.apis.notifications.repository import \
    NotificationSubscriptionRepository
from app.apis.notifications.types import (DeliveryStatus, NotificationChannel,
                                          NotificationRecipientType)
from app.apis.users.repository import UserRepository
from app.core.database.base import HomeId, NotificationEventId

logger = logging.getLogger(__name__)


class NotificationIngestService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.sub_repo = NotificationSubscriptionRepository(session)
        self.user_repo = UserRepository(session)

    async def handle_inventory_event(
        self, *, topic: str, payload: dict, headers: dict
    ) -> None:
        logger.warning(
            "INGEST class=%s module=%s", type(self).__name__, type(self).__module__
        )

        event_id = NotificationEventId(UUID(payload["event_id"]))
        home_id = HomeId(UUID(payload["home_id"]))

        event = NotificationEvent(
            id=event_id,
            source="inventory",
            event_type=topic,
            subject=self._subject(topic, payload),
            message=self._message(topic, payload),
            recipients={},
        )

        # NOTE: do NOT open session.begin() here if caller already did session.begin()
        try:
            async with self.session.begin_nested():
                self.session.add(event)
                await self.session.flush()
            logger.info("INGEST event insert OK event_id=%s", event_id)

        except IntegrityError:
            logger.info(
                "INGEST event already exists event_id=%s (idempotent)", event_id
            )
            existing = await self.session.get(NotificationEvent, event_id)
            if existing is None:
                raise
            event = existing

        subs = await self.sub_repo.list_enabled_for_topic(home_id=home_id, topic=topic)
        logger.info(
            "INGEST fetched subs=%d home_id=%s topic=%s", len(subs), home_id, topic
        )
        if not subs:
            return

        user_ids = list({s.user_id for s in subs})
        users = await self.user_repo.get_users_by_ids(user_ids)
        user_by_id = {u.id: u for u in users}

        deliveries: list[NotificationDelivery] = []
        for s in subs:
            user = user_by_id.get(s.user_id)
            if not user:
                continue

            # target is optional (don’t crash if column not added yet)
            target = getattr(s, "target", None)

            recipient_type, recipient = self._resolve_recipient(s.channel, user, target)
            if not recipient:
                continue

            deliveries.append(
                NotificationDelivery(
                    event_id=event.id,
                    channel=s.channel,
                    recipient_type=recipient_type,
                    recipient=recipient,
                    status=DeliveryStatus.PENDING,
                )
            )

        if deliveries:
            self.session.add_all(deliveries)
            await self.session.flush()
            logger.info(
                "INGEST created deliveries=%d event_id=%s", len(deliveries), event_id
            )

    def _resolve_recipient(
        self, channel: NotificationChannel, user, target: dict | None
    ):
        target = target or {}

        if channel == NotificationChannel.EMAIL:
            email = target.get("email") or getattr(user, "email", None)
            return NotificationRecipientType.EMAIL, email

        if channel == NotificationChannel.SMS:
            phone = target.get("phone") or getattr(user, "phone", None)
            return NotificationRecipientType.PHONE, phone

        if channel == NotificationChannel.LOG:
            return NotificationRecipientType.LOG, "stdout"

        return None, None

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
