from uuid import uuid4

import pytest

from app.apis.notifications.types import (DeliveryStatus, NotificationChannel,
                                          NotificationRecipientType)
from app.apis.notifications.worker.handlers import (ClaimedDelivery,
                                                    send_claimed_deliveries)


class RecordingEmailSender:
    channel = NotificationChannel.EMAIL

    def __init__(self):
        self.sent = []

    async def send(self, *, recipient, subject, message, headers=None):
        self.sent.append(
            {
                "recipient": recipient,
                "subject": subject,
                "message": message,
                "headers": dict(headers or {}),
            }
        )
        return "email_sent"


def _claimed_email_delivery(channel):
    return ClaimedDelivery(
        id=uuid4(),
        channel=channel,
        recipient_type=NotificationRecipientType.EMAIL,
        recipient="family.inventory.app@gmail.com",
        attempt_count=1,
        max_attempts=5,
        status=DeliveryStatus.SENDING,
    )


@pytest.mark.asyncio
async def test_send_claimed_deliveries_sends_email_channel_enum():
    sender = RecordingEmailSender()
    claimed = _claimed_email_delivery(NotificationChannel.EMAIL)

    results = await send_claimed_deliveries(
        claimed=[claimed],
        subject="Expiring soon",
        message="Milk expires tomorrow",
        headers={"topic": "inventory.item.expiring_soon"},
        senders={NotificationChannel.EMAIL: sender},
    )

    assert results[0].delivery_id == claimed.id
    assert results[0].status == DeliveryStatus.SENT
    assert results[0].last_error is None
    assert sender.sent == [
        {
            "recipient": "family.inventory.app@gmail.com",
            "subject": "Expiring soon",
            "message": "Milk expires tomorrow",
            "headers": {
                "topic": "inventory.item.expiring_soon",
                "routing_key": "inventory.item.expiring_soon",
                "x-original-topic": "inventory.item.expiring_soon",
                "x-original-routing-key": "inventory.item.expiring_soon",
            },
        }
    ]


@pytest.mark.asyncio
async def test_send_claimed_deliveries_sends_email_channel_string():
    sender = RecordingEmailSender()
    claimed = _claimed_email_delivery("email")

    results = await send_claimed_deliveries(
        claimed=[claimed],
        subject="Expiring soon",
        message="Milk expires tomorrow",
        headers={"topic": "inventory.item.expiring_soon"},
        senders={NotificationChannel.EMAIL: sender},
    )

    assert results[0].delivery_id == claimed.id
    assert results[0].status == DeliveryStatus.SENT
    assert results[0].last_error is None
    assert sender.sent[0]["recipient"] == "family.inventory.app@gmail.com"
