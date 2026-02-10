from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.apis.notifications.types import (NotificationChannel,
                                          NotificationSource)
from app.core.database.base import HomeId, NotificationEventId, UserId
from app.schemas_base.base import BaseApiSchema


class NotificationRecipient(BaseModel):
    channel: NotificationChannel
    recipient: str  # email address, phone, slack channel id, user_id, etc.


class NotificationRequest(BaseModel):
    # If caller doesn't provide, we generate in service.
    event_id: NotificationEventId | None = None

    source: NotificationSource = Field(
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
    event_id: NotificationEventId
    accepted: bool
    deliveries: list[NotificationDeliveryResult]
    created_at: datetime


class SubscriptionCreateRequest(BaseApiSchema):
    home_id: HomeId
    topic: str = Field(
        ..., min_length=1, max_length=200
    )  # e.g. inventory.item.expired or inventory.item.*
    channel: NotificationChannel
    enabled: bool = True


class SubscriptionUpdate(BaseApiSchema):
    topic: str | None = Field(default=None, min_length=1, max_length=200)
    channel: NotificationChannel | None = None
    enabled: bool | None = None


class SubscriptionOut(BaseApiSchema):
    id: UUID
    home_id: HomeId
    user_id: UserId
    topic: str
    channel: NotificationChannel
    enabled: bool
    created_at: datetime
    updated_at: datetime | None = None
    deleted_at: datetime | None = None


class InAppNotificationOut(BaseApiSchema):

    id: UUID
    event_id: NotificationEventId
    home_id: HomeId
    subject: str | None
    message: str
    read_at: datetime | None
    created_at: datetime
