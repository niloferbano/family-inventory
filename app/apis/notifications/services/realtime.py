import json
from typing import Any
from uuid import UUID

from redis.asyncio import Redis  # redis-py >= 4

from app.apis.notifications.models import InAppNotification


class NotificationRealtimeService:
    """Real-time push for in-app notifications.

    This is an optional layer on top of the DB-backed inbox.

    - Local/dev: can run without Redis (no-op).
    - Production/multi-replica: configure Redis and publish per-user events.

    The websocket/SSE layer should subscribe to `notifications.inapp.<user_id>`.
    """

    CHANNEL_PREFIX = "notifications.in_app."

    def __init__(self, redis: Redis | None = None):
        self.redis = redis

    def _channel_for_user(self, user_id: UUID) -> str:
        return f"{self.CHANNEL_PREFIX}{user_id}"

    async def publish_in_app(self, *, user_id: UUID, payload: dict[str, Any]) -> None:
        """Publish a push event for a user (best-effort)."""
        if self.redis is None:
            return
        channel = self._channel_for_user(user_id)
        # NOTE: Redis pubsub payload must be bytes/str
        await self.redis.publish(channel, json.dumps(payload, default=str))

    async def publish_in_app_from_row(self, *, row: InAppNotification) -> None:
        """Convenience helper: publish using the persisted inbox row."""
        await self.publish_in_app(
            user_id=row.user_id,
            payload={
                "type": "notification.in_app.created",
                "data": {
                    "id": str(row.id),
                    "event_id": str(row.event_id),
                    "home_id": str(row.home_id),
                    "topic": getattr(row, "topic", None),
                    "subject": row.subject,
                    "message": row.message,
                    "read_at": row.read_at.isoformat() if row.read_at else None,
                    "created_at": (
                        row.created_at.isoformat() if row.created_at else None
                    ),
                },
            },
        )
