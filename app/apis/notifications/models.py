from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (ForeignKey, Index, Integer, String, Text,
                        UniqueConstraint)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.apis.notifications.types import (DeliveryStatus, NotificationChannel,
                                          NotificationRecipientType)
from app.core.database.base import SQLBase, TimeStampMixin

# Reuse enum types across models so SQLAlchemy doesn't create multiple objects
# with the same Postgres enum name.
notification_channel_enum = SAEnum(
    NotificationChannel,
    name="notification_channel_enum",
    values_callable=lambda e: [x.value for x in e],
    native_enum=True,
)

notification_recipient_type_enum = SAEnum(
    NotificationRecipientType,
    name="notification_recipient_type_enum",
    values_callable=lambda e: [x.value for x in e],
    native_enum=True,
)

notification_delivery_status_enum = SAEnum(
    DeliveryStatus,
    name="notification_delivery_status_enum",
    values_callable=lambda e: [x.value for x in e],
    native_enum=True,
)


class NotificationEvent(SQLBase, TimeStampMixin):
    __tablename__ = "notification_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )

    source: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)

    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    recipients: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )

    deliveries: Mapped[list["NotificationDelivery"]] = relationship(
        "NotificationDelivery",
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class NotificationDelivery(SQLBase, TimeStampMixin):
    __tablename__ = "notification_deliveries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )

    # FK to NotificationEvent.id
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    recipient_type: Mapped[NotificationRecipientType] = mapped_column(
        notification_recipient_type_enum,
        nullable=False,
    )
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        notification_channel_enum,
        nullable=False,
        index=True,
    )

    status: Mapped[DeliveryStatus] = mapped_column(
        notification_delivery_status_enum,
        nullable=False,
        default=DeliveryStatus.PENDING,
        index=True,
    )

    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    next_retry_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    event: Mapped["NotificationEvent"] = relationship(
        "NotificationEvent",
        back_populates="deliveries",
    )
    locked_by: Mapped[str | None] = mapped_column(
        String(120), nullable=True, index=True
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    lock_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "channel",
            "recipient_type",
            "recipient",
            name="uq_delivery_per_target",
        ),
    )


class InAppNotification(SQLBase, TimeStampMixin):
    __tablename__ = "in_app_notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        nullable=False,
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notification_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    home_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("homes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    subject: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    __table_args__ = (
        Index("ix_notification_inbox_user_read", "user_id", "read_at"),
        UniqueConstraint(
            "event_id",
            "user_id",
            name="uq_inbox_user_event",
        ),
    )


class NotificationOutbox(SQLBase, TimeStampMixin):
    __tablename__ = "notification_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), unique=True, nullable=False
    )

    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )  # PENDING|SENT|FAILED
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_outbox_status_next_retry", "status", "next_retry_at"),)


class NotificationSubscription(SQLBase, TimeStampMixin):
    __tablename__ = "notification_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid4
    )

    home_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("homes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    topic: Mapped[str] = mapped_column(String(200), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(
        notification_channel_enum,
        nullable=False,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(
        sa.Boolean(),
        nullable=False,
        default=True,
        server_default=sa.text("true"),
    )

    target: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=sa.text("'{}'::jsonb"),
    )

    __table_args__ = (
        UniqueConstraint(
            "home_id",
            "user_id",
            "topic",
            "channel",
            name="uq_notification_subscription_target",
        ),
    )
