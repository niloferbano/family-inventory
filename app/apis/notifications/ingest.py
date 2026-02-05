from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
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
from app.core.logging import get_logger

logger = get_logger(__name__)


class NotificationIngestService:
    def __init__(
        self,
        session: AsyncSession,
    ):
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

        subject = self._subject(topic, payload)
        message = self._message(topic, payload)

        event = NotificationEvent(
            id=event_id,
            source="inventory",
            event_type=topic,
            subject=subject,
            message=message,
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

        delivery_rows: list[dict] = []
        for s in subs:
            user = user_by_id.get(s.user_id)
            if not user:
                continue

            # target is optional (don’t crash if column not added yet)
            target = getattr(s, "target", None)

            recipient_type, recipient = self._resolve_recipient(s.channel, user, target)
            if not recipient_type or not recipient:
                continue

            # Create a delivery row for every channel (including IN_APP).
            # ChannelSender implementations decide what “send” means per channel.
            delivery_rows.append(
                {
                    "event_id": event.id,
                    "channel": s.channel,
                    "recipient_type": recipient_type,
                    "recipient": recipient,
                    "status": DeliveryStatus.PENDING,
                }
            )

        if delivery_rows:
            stmt = (
                pg_insert(NotificationDelivery)
                .values(delivery_rows)
                .on_conflict_do_update(
                    constraint="uq_delivery_per_target",
                    # idempotent: keep the existing row, just bump updated_at
                    set_={"updated_at": sa.func.now()},
                )
            )
            await self.session.execute(stmt)
            # rowcount can be -1 on some drivers; log input size instead.
            logger.info(
                "INGEST upserted deliveries=%d event_id=%s",
                len(delivery_rows),
                event_id,
            )

    def _resolve_recipient(
        self, channel: NotificationChannel, user, target: dict | None
    ) -> tuple[NotificationRecipientType | None, str | None]:
        target = target or {}

        if channel == NotificationChannel.EMAIL:
            email = target.get("email") or getattr(user, "email", None)
            return NotificationRecipientType.EMAIL, email

        if channel == NotificationChannel.SMS:
            phone = target.get("phone") or getattr(user, "phone", None)
            return NotificationRecipientType.PHONE, phone

        if channel == NotificationChannel.LOG:
            return NotificationRecipientType.LOG, "stdout"

        if channel in (NotificationChannel.IN_APP, NotificationChannel.PUSH):
            return NotificationRecipientType.IN_APP_USER, str(getattr(user, "id", ""))

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
