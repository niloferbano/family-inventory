from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.models import InAppNotification
from app.apis.notifications.types import NotificationChannel
from app.core.database.base import HomeId, NotificationEventId, UserId
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
        event_id_raw = h.get("x-event-id") or h.get("event_id")
        home_id_raw = h.get("home_id")
        topic = h.get("x-original-topic") or h.get("topic") or h.get("routing_key")

        if not event_id_raw:
            raise ValueError(
                "Missing event id in headers (expected x-event-id or event_id)"
            )
        if not home_id_raw:
            raise ValueError("Missing home_id in headers (expected home_id)")
        if not topic:
            topic = "unknown"

        event_id = NotificationEventId(str(event_id_raw))
        home_id = HomeId(str(home_id_raw))

        row = {
            "user_id": user_id,
            "home_id": home_id,
            "event_id": event_id,
            "topic": str(topic),
            "subject": subject,
            "message": message,
            "data": h,
        }

        async with self.sessionmaker() as session:
            async with session.begin():
                stmt = (
                    pg_insert(InAppNotification)
                    .values(row)
                    .on_conflict_do_nothing(constraint="uq_inbox_user_event")
                )
                await session.execute(stmt)

        logger.info(
            "[NOTIFY][IN-APP] stored inbox row user_id=%s event_id=%s topic=%s",
            user_id,
            event_id,
            topic,
        )
        return "stored"
