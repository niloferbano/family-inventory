from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from app.apis.notifications.types import NotificationChannel
from app.core.logging import configure_logging, get_logger

configure_logging()
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
            "[NOTIFY][LOG]",
            {
                "recipient": recipient,
                "subject": subject,
                "message": message,
                "headers": dict(headers or {}),
            },
        )
        return "logged"


@dataclass
class InAppSender:
    channel: NotificationChannel = NotificationChannel.PUSH

    async def send(
        self,
        *,
        recipient: str,
        subject: str | None,
        message: str,
        headers: Mapping[str, Any] | None = None,
    ) -> str:
        logger.info(
            "[NOTIFY][PUSH]",
            {
                "recipient": recipient,
                "subject": subject,
                "message": message,
                "headers": dict(headers or {}),
            },
        )
        return "in_app"
