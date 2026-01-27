import uuid

import pytest
from sqlalchemy import select

from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent,
                                           NotificationOutbox)
from app.apis.notifications.schema import NotificationRequest
from app.apis.notifications.service import NotificationService
from app.apis.notifications.types import DeliveryStatus, NotificationChannel
from app.apis.notifications.worker.handlers import process_event


class _StubSender:
    channel = NotificationChannel.PUSH

    async def send(
        self, *, recipient: str, subject: str | None, message: str, metadata: dict
    ) -> str:
        return "ok"


@pytest.mark.asyncio
async def test_notification_service_persists_event_and_outbox(db_session):
    request = NotificationRequest(
        source="inventory",
        event_type="inventory.item.expiring_soon",
        subject="Milk is expiring soon",
        message="Milk expires in 2 days",
        recipients=[{"channel": "push", "recipient": "user-123"}],
    )

    service = NotificationService(session=db_session)
    response = await service.send(request)
    await db_session.commit()

    saved_event = await db_session.get(NotificationEvent, response.event_id)
    assert saved_event is not None
    assert saved_event.source == "inventory"
    assert saved_event.event_type == "inventory.item.expiring_soon"
    assert saved_event.recipients[0]["recipient"] == "user-123"

    outbox = (
        await db_session.execute(
            select(NotificationOutbox).where(
                NotificationOutbox.event_id == response.event_id
            )
        )
    ).scalar_one()

    assert outbox.topic == "notifications.send"
    assert outbox.payload["event_id"] == str(response.event_id)
    assert outbox.payload["source"] == "inventory"
    assert outbox.payload["recipients"][0]["recipient"] == "user-123"
    assert response.accepted is True
    assert response.deliveries[0].accepted is True


@pytest.mark.asyncio
async def test_inventory_notification_consumed_by_worker(db_session):
    event_id = uuid.uuid4()
    request = NotificationRequest(
        event_id=event_id,
        source="inventory",
        event_type="inventory.item.expired",
        subject="Bread expired",
        message="Bread expired yesterday",
        recipients=[{"channel": "push", "recipient": "user-999"}],
    )

    service = NotificationService(session=db_session)
    response = await service.send(request)
    await db_session.commit()

    outbox_payload = (
        await db_session.execute(
            select(NotificationOutbox.payload).where(
                NotificationOutbox.event_id == response.event_id
            )
        )
    ).scalar_one()
    assert outbox_payload["event_id"] == str(event_id)

    # Simulate worker consuming the published notification
    async with db_session.begin():
        await process_event(
            db_session,
            payload=outbox_payload,
            senders={NotificationChannel.PUSH: _StubSender()},
        )

    delivery = (
        await db_session.execute(
            select(NotificationDelivery).where(
                NotificationDelivery.event_id == response.event_id
            )
        )
    ).scalar_one()

    assert delivery.recipient == "user-999"
    assert delivery.channel == NotificationChannel.PUSH
    assert delivery.status == DeliveryStatus.SENT
    assert delivery.attempt_count == 1
