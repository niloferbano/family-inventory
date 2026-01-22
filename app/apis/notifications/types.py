from enum import StrEnum
from typing import Any, TypedDict


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationRecipientType(StrEnum):
    EMAIL = "email"
    PHONE = "phone"
    SLACK_CHANNEL = "slack_channel"
    IN_APP_USER = "in_app_user"
    LOG = "log"


class DeliveryStatus(StrEnum):
    PENDING = "pending"  # created, not yet attempted
    SENDING = "sending"  # worker locked & is processing
    SENT = "sent"  # successfully delivered
    FAILED = "failed"  # failed but retryable (next_retry_at set)
    DLQ = "dlq"


class RecipientPayload(TypedDict):
    channel: str
    recipient: str
    metadata: dict[str, Any]


class NotificationMessage(TypedDict):
    event_id: str
    source: str
    event_type: str
    subject: str | None
    message: str
    recipients: list[RecipientPayload]
    created_at: str
