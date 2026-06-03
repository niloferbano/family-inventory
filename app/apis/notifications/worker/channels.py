from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Mapping, Protocol
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.models import InAppNotification
from app.apis.notifications.services.realtime import \
    NotificationRealtimeService
from app.apis.notifications.types import NotificationChannel
from app.core.configs.config import settings
from app.core.database.base import HomeId, NotificationEventId, UserId
from app.core.database.session import session_scope
from app.core.logging import get_logger

logger = get_logger(__name__)


class ChannelSender(Protocol):
    channel: NotificationChannel

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        message: str,
        headers: Mapping[str, Any] | None = None,
    ) -> str:
        """
        Return a detail string (e.g., provider msg id).

        NOTE: For in-app notifications we persist to the DB inbox table; sending is a no-op.
        Raise exception to trigger retry.
        """


@dataclass
class LogSender:
    channel: NotificationChannel = NotificationChannel.LOG

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        message: str,
        headers: Mapping[str, Any] | None = None,
    ) -> str:
        logger.info(
            "[NOTIFY][LOG] recipient=%s subject=%s message=%s headers=%s",
            recipient,
            subject,
            message,
            dict(headers or {}),
        )
        return "logged"


@dataclass
class InAppSender:
    """Persist notifications into the in-app inbox table."""

    sessionmaker: async_sessionmaker[AsyncSession]
    realtime: NotificationRealtimeService | None = None
    channel: NotificationChannel = NotificationChannel.IN_APP

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        message: str,
        headers: Mapping[str, Any] | None = None,
    ) -> str:
        h = dict(headers or {})

        logger.info(
            "[NOTIFY][IN-APP] recipient=%s subject=%s message=%s headers=%s",
            recipient,
            subject,
            message,
            h,
        )

        # recipient is expected to be the user_id (UUID string)
        try:
            user_id = UserId(UUID(str(recipient)))
        except Exception as exc:
            raise TypeError(f"Invalid in-app recipient user_id: {recipient}") from exc

        # required context for inbox row
        event_id_raw = (
            h.get("x-event-id")
            or h.get("event_id")
            or h.get("message_id")
            or h.get("correlation_id")
        )
        home_id_raw = h.get("home_id") or h.get("x-home-id")
        topic = (
            h.get("x-original-routing-key")
            or h.get("x-original-topic")
            or h.get("topic")
            or h.get("routing_key")
        )

        if not topic:
            topic = "unknown"
        topic = str(topic)

        if not event_id_raw:
            raise ValueError(
                "Missing event id in headers (expected x-event-id or event_id)"
            )
        if not home_id_raw:
            raise ValueError("Missing home_id in headers (expected home_id)")

        event_id = NotificationEventId(UUID(str(event_id_raw)))
        home_id = HomeId(UUID(str(home_id_raw)))

        row: dict[str, Any] = {
            "user_id": user_id,
            "home_id": home_id,
            "event_id": event_id,
            "subject": subject,
            "message": message,
        }

        # Some schemas include these optional columns.
        if hasattr(InAppNotification, "topic"):
            row["topic"] = topic
        if hasattr(InAppNotification, "data"):
            row["data"] = h

        stored_id: str | None = None
        stored_row: InAppNotification | None = None

        async with session_scope(self.sessionmaker) as session:
            async with session.begin():
                stmt = (
                    pg_insert(InAppNotification)
                    .values(row)
                    .on_conflict_do_nothing(constraint="uq_inbox_user_event")
                    .returning(InAppNotification.id)
                )
                res = await session.execute(stmt)
                inserted_id = res.scalar_one_or_none()

                # If we hit ON CONFLICT DO NOTHING, Postgres returns 0 rows.
                # Fetch the existing row id so callers can still proceed.
                if inserted_id is None:
                    inserted_id = await session.scalar(
                        sa.select(InAppNotification.id).where(
                            InAppNotification.event_id == event_id,
                            InAppNotification.user_id == user_id,
                        )
                    )

                if inserted_id is not None:
                    stored_id = str(inserted_id)
                    stored_row = await session.get(InAppNotification, inserted_id)

        # Real-time publish requires the full row (not just the id)
        if stored_row is not None and self.realtime is not None:
            try:
                await self.realtime.publish_in_app_from_row(row=stored_row)
            except Exception:
                logger.exception(
                    "[NOTIFY][IN-APP] realtime publish failed user_id=%s event_id=%s",
                    user_id,
                    event_id,
                )

        logger.info(
            "[NOTIFY][IN-APP] inbox row user_id=%s event_id=%s topic=%s stored_id=%s",
            user_id,
            event_id,
            topic,
            stored_id,
        )
        return "stored"


@dataclass
class EmailSender:
    channel: NotificationChannel = NotificationChannel.EMAIL

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        message: str | None,
        headers: Mapping[str, Any] | None = None,
    ) -> str:
        msg = EmailMessage()
        msg["Subject"] = subject or ""
        msg["From"] = settings.SMTP.from_email
        msg["To"] = recipient
        msg.set_content(message or "")

        context = ssl.create_default_context()
        if settings.SMTP.use_ssl:
            with smtplib.SMTP_SSL(
                settings.SMTP.host,
                settings.SMTP.port,
                context=context,
            ) as server:
                if settings.SMTP.username and settings.SMTP.password:
                    server.login(settings.SMTP.username, settings.SMTP.password)
                server.send_message(msg)

        else:
            with smtplib.SMTP(settings.SMTP.host, settings.SMTP.port) as server:
                if settings.SMTP.use_tls:
                    server.starttls(context=context)
                if settings.SMTP.username and settings.SMTP.password:
                    server.login(settings.SMTP.username, settings.SMTP.password)
                server.send_message(msg)

        return "email_sent"
