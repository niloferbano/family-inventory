from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.apis.notifications.types import NotificationChannel


class ChannelSender(Protocol):
    channel: NotificationChannel

    async def send(
        self, *, recipient: str, subject: str | None, message: str, metadata: dict
    ) -> str:
        """
        Return a detail string (e.g., provider msg id).
        Raise exception to trigger retry.
        """


@dataclass
class LogSender:
    channel: NotificationChannel = NotificationChannel.LOG

    async def send(
        self, *, recipient: str, subject: str | None, message: str, metadata: dict
    ) -> str:
        print(
            "[NOTIFY][LOG]",
            {
                "recipient": recipient,
                "subject": subject,
                "message": message,
                "metadata": metadata,
            },
        )
        return "logged"
