from uuid import uuid4

import pytest

from app.apis.notifications.types import (
    DeliveryStatus,
    NotificationChannel,
    NotificationRecipientType,
)
from app.apis.notifications.worker.handlers import (
    ClaimedDelivery,
    send_claimed_deliveries,
)


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


@pytest.mark.asyncio
async def test_email_includes_safe_hyperlink_and_plain_text(monkeypatch):
    from unittest.mock import MagicMock

    from app.apis.notifications.worker import channels
    from app.core.configs.config import settings

    smtp = MagicMock()
    monkeypatch.setattr(channels.smtplib, "SMTP", MagicMock(return_value=smtp))
    monkeypatch.setattr(settings.SMTP, "use_ssl", False)
    monkeypatch.setattr(settings.SMTP, "use_tls", False)
    link = 'http://localhost:5173/activate/abc&x="value"'
    text = "<script>unsafe</script>\n" + link
    await channels.EmailSender().send(
        recipient="test@example.com", subject="Activate", message=text
    )
    email = smtp.__enter__.return_value.send_message.call_args.args[0]
    assert email.get_body(preferencelist=("plain",)).get_content().strip() == text
    html = email.get_body(preferencelist=("html",)).get_content()
    assert (
        '<a href="http://localhost:5173/activate/abc&amp;x=&quot;value&quot;">' in html
    )
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
