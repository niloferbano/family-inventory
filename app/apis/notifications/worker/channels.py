from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.models import InAppNotification
from app.apis.notifications.services.realtime import \
    NotificationRealtimeService
from app.apis.notifications.types import NotificationChannel
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
            user_id = UserId(str(recipient))
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

        event_id = NotificationEventId(str(event_id_raw))
        home_id = HomeId(str(home_id_raw))

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

        async with session_scope(self.sessionmaker) as session:
            async with session.begin():
                stmt = (
                    pg_insert(InAppNotification)
                    .values(row)
                    .on_conflict_do_nothing(
                        constraint="uq_notification_inbox_event_user"
                    )
                    .returning(InAppNotification)
                )
                res = await session.execute(stmt)
                stored = res.scalar_one_or_none()

        if stored is not None and self.realtime is not None:
            try:
                await self.realtime.publish_in_app_from_row(row=stored)
            except Exception:
                logger.exception(
                    "[NOTIFY][IN-APP] realtime publish failed user_id=%s event_id=%s",
                    user_id,
                    event_id,
                )

        logger.info(
            "[NOTIFY][IN-APP] stored inbox row user_id=%s event_id=%s topic=%s",
            user_id,
            event_id,
            topic,
        )
        return "stored"
