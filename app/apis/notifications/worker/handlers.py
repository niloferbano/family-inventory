from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent)
from app.apis.notifications.types import (DeliveryStatus, NotificationChannel,
                                          NotificationRecipientType)
from app.apis.notifications.worker.channels import ChannelSender


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_event_exists(
    session: AsyncSession,
    *,
    event_id,
    payload: dict[str, Any],
) -> NotificationEvent:
    """
    If you already persist NotificationEvent at produce-time, you can skip this.
    If events may come from other services, it's useful to upsert here for audit.
    """
    event = await session.get(NotificationEvent, event_id)
    if event:
        return event

    event = NotificationEvent(
        id=event_id,
        source=payload["source"],
        event_type=payload["event_type"],
        subject=payload.get("subject"),
        message=payload["message"],
        recipients={"recipients": payload.get("recipients", [])},
    )
    session.add(event)
    await session.flush()
    return event


async def upsert_delivery(
    session: AsyncSession,
    *,
    event_id,
    channel: NotificationChannel,
    recipient_type: NotificationRecipientType,
    recipient: str,
    max_attempts: int = 5,
) -> NotificationDelivery:
    """
    Idempotent per (event_id, channel, recipient_type, recipient).
    Uses  uq_delivery_per_target constraint.
    """
    delivery = NotificationDelivery(
        event_id=event_id,
        channel=channel,
        recipient_type=recipient_type,
        recipient=recipient,
        status=DeliveryStatus.PENDING,
        attempt_count=0,
        max_attempts=max_attempts,
    )
    session.add(delivery)

    try:
        await session.flush()
        return delivery
    except IntegrityError:
        # already exists — load it
        await session.rollback()
        stmt = select(NotificationDelivery).where(
            NotificationDelivery.event_id == event_id,
            NotificationDelivery.channel == channel,
            NotificationDelivery.recipient_type == recipient_type,
            NotificationDelivery.recipient == recipient,
        )
        return (await session.execute(stmt)).scalar_one()


async def process_event(
    session: AsyncSession,
    *,
    payload: dict[str, Any],
    senders: dict[NotificationChannel, ChannelSender],
) -> None:
    """
    Writes Delivery rows + sends all recipients.
    Any exception should be handled in consumer layer for retry/DLQ.
    """
    event_id = payload["event_id"]

    # optional (audit) - safe if already exists
    await ensure_event_exists(session, event_id=event_id, payload=payload)

    recipients = payload.get("recipients", [])
    # subject = payload.get("subject")
    # message = payload["message"]

    for r in recipients:
        channel = NotificationChannel(r["channel"])
        recipient = r["recipient"]
        recipient_type = NotificationRecipientType(r.get("recipient_type", "log"))
        # metadata = r.get("metadata") or {}

        sender = senders.get(channel)
        if not sender:
            # no sender configured => mark failed immediately
            delivery = await upsert_delivery(
                session,
                event_id=event_id,
                channel=channel,
                recipient_type=recipient_type,
                recipient=recipient,
            )
            delivery.status = DeliveryStatus.FAILED
            delivery.last_error = f"Unsupported channel: {channel}"
            delivery.last_attempt_at = _utcnow()
            continue

        delivery = await upsert_delivery(
            session,
            event_id=event_id,
            channel=channel,
            recipient_type=recipient_type,
            recipient=recipient,
        )

        # Already succeeded? (idempotent replays)
        if delivery.status == DeliveryStatus.SENT:
            continue

        # attempt
        delivery.attempt_count += 1
        delivery.last_attempt_at = _utcnow()

        # detail = await sender.send(
        #     recipient=recipient,
        #     subject=subject,
        #     message=message,
        #     metadata=metadata,
        # )

        delivery.status = DeliveryStatus.SENT
        delivery.last_error = None
        delivery.next_retry_at = None
