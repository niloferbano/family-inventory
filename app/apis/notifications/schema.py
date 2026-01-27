from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.apis.notifications.types import NotificationChannel
from app.schemas_base.base import BaseApiSchema


class NotificationRecipient(BaseModel):
    channel: NotificationChannel
    recipient: str  # email address, phone, slack channel id, user_id, etc.


class NotificationRequest(BaseModel):
    # If caller doesn't provide, we generate in service.
    event_id: UUID | None = None

    source: str = Field(
        ..., description="Service emitting this notification (e.g. inventory)"
    )
    event_type: str = Field(
        ..., description="Domain event name (e.g. inventory.expiring_soon)"
    )

    subject: str | None = None
    message: str

    recipients: list[NotificationRecipient]


class NotificationDeliveryResult(BaseApiSchema):
    channel: NotificationChannel
    recipient: str
    accepted: bool
    detail: str | None = None


class NotificationResponse(BaseApiSchema):
    event_id: UUID
    accepted: bool
    deliveries: list[NotificationDeliveryResult]
    created_at: datetime
