import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

import sqlalchemy as sa

try:
    from redis.asyncio import Redis  # redis-py >= 4
except Exception:  # pragma: no cover
    Redis = None  # type: ignore

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homeuser.repository import HomeUserRepository
from app.apis.notifications.models import (InAppNotification,
                                           NotificationEvent,
                                           NotificationOutbox,
                                           NotificationSubscription)
from app.apis.notifications.repository import \
    NotificationSubscriptionRepository
from app.apis.notifications.schema import (InAppNotificationOut,
                                           NotificationDeliveryResult,
                                           NotificationRequest,
                                           NotificationResponse,
                                           SubscriptionCreateRequest,
                                           SubscriptionUpdate)
from app.core.database.base import HomeId, UserId
from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import (DomainConflictError,
                                          DomainNotFoundError,
                                          DomainPermissionError)


class NotificationService:
    def __init__(self, session):
        self.session = session

    async def send(self, req: NotificationRequest) -> NotificationResponse:
        event_id = req.event_id or uuid4()

        recipients = [
            {
                "channel": r.channel.value,
                "recipient": r.recipient,
            }
            for r in req.recipients
        ]

        event = NotificationEvent(
            id=event_id,  # use event_id as PK to keep it simple
            source=req.source,
            event_type=req.event_type,
            subject=req.subject,
            message=req.message,
            recipients=recipients,
        )

        outbox = NotificationOutbox(
            event_id=event_id,
            topic="notifications.send",  # or req.event_type if you want
            payload={
                "event_id": str(event_id),
                "source": req.source,
                "event_type": req.event_type,
                "subject": req.subject,
                "message": req.message,
                "recipients": recipients,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            headers={"source": req.source},
        )

        try:
            # SAVEPOINT keeps session usable even if caller wraps in begin()
            async with self.session.begin_nested():
                self.session.add(event)
                self.session.add(outbox)
                await self.session.flush()
        except IntegrityError as exc:
            raise DomainConflictError(
                code=ErrorCode.NOTIFICATION_EVENT_DUPLICATE,
                message="Notification event already exists (idempotent replay).",
                details={"event_id": str(event_id)},
            ) from exc

        return NotificationResponse(
            event_id=event_id,
            accepted=True,
            deliveries=[
                NotificationDeliveryResult(
                    channel=r.channel, recipient=r.recipient, accepted=True, detail=None
                )
                for r in req.recipients
            ],
            created_at=datetime.now(timezone.utc),
        )


class NotificationPreferencesService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = NotificationSubscriptionRepository(session)
        self.home_user_repo = HomeUserRepository(session)

    async def list_my_subscriptions(
        self, *, user_id: UUID, home_id: UUID | None = None
    ):
        return await self.repo.list_for_user(user_id=user_id, home_id=home_id)

    async def create_subscription(
        self, *, user_id: UUID, req: SubscriptionCreateRequest
    ) -> NotificationSubscription:
        # business/authz hook
        await self._require_home_member(home_id=req.home_id, user_id=user_id)

        sub = NotificationSubscription(
            home_id=req.home_id,
            user_id=user_id,
            topic=req.topic,
            channel=req.channel,
            enabled=req.enabled,
        )

        try:
            await self.repo.create(sub)
        except IntegrityError as exc:
            raise DomainConflictError(
                code=ErrorCode.SUBSCRIPTION_DUPLICATE,
                message="Subscription already exists for (home_id, topic, channel).",
                details={
                    "home_id": str(req.home_id),
                    "topic": req.topic,
                    "channel": req.channel.value,
                },
            ) from exc

        return sub

    async def update_subscription(
        self, *, user_id: UUID, subscription_id: UUID, req: SubscriptionUpdate
    ) -> NotificationSubscription:
        sub = await self.repo.get(sub_id=subscription_id)
        if not sub:
            raise DomainNotFoundError(
                code=ErrorCode.SUBSCRIPTION_NOT_FOUND,
                message="Subscription not found.",
            )

        if sub.user_id != user_id:
            raise DomainPermissionError(
                code=ErrorCode.SUBSCRIPTION_FORBIDDEN,
                message="Not allowed.",
            )

        await self._require_home_member(home_id=sub.home_id, user_id=user_id)

        if req.topic is not None:
            sub.topic = req.topic
        if req.channel is not None:
            sub.channel = req.channel
        if req.enabled is not None:
            sub.enabled = req.enabled

        try:
            async with self.session.begin():
                self.session.add(sub)
                await self.session.flush()
        except IntegrityError as exc:
            raise DomainConflictError(
                code=ErrorCode.SUBSCRIPTION_DUPLICATE,
                message="Update would create a duplicate subscription.",
                details={"subscription_id": str(subscription_id)},
            ) from exc

        return sub

    async def delete_subscription(
        self, *, user_id: UUID, subscription_id: UUID
    ) -> None:
        sub = await self.repo.get(sub_id=subscription_id)
        if not sub:
            return

        if sub.user_id != user_id:
            raise DomainPermissionError(
                code=ErrorCode.SUBSCRIPTION_FORBIDDEN,
                message="Not allowed.",
            )

        await self._require_home_member(home_id=sub.home_id, user_id=user_id)

        async with self.session.begin():
            await self.repo.delete(sub)

    async def _require_home_member(self, *, home_id: UUID, user_id: UUID) -> None:
        has_access = await self.home_user_repo.user_has_access(
            UserId(user_id),
            HomeId(home_id),
        )
        if not has_access:
            raise DomainPermissionError(
                code=ErrorCode.HOME_PERMISSION_DENIED,
                message="User doesn't have access to this home.",
                details={"home_id": str(home_id), "user_id": str(user_id)},
            )


class NotificationRealtimeService:
    """Real-time push for in-app notifications.

    This is an optional layer on top of the DB-backed inbox.

    - Local/dev: can run without Redis (no-op).
    - Production/multi-replica: configure Redis and publish per-user events.

    The websocket/SSE layer should subscribe to `notifications.inapp.<user_id>`.
    """

    CHANNEL_PREFIX = "notifications.inapp."

    def __init__(self, redis: "Redis | None" = None):
        self.redis = redis

    def _channel_for_user(self, user_id: UUID) -> str:
        return f"{self.CHANNEL_PREFIX}{user_id}"

    async def publish_inapp(self, *, user_id: UUID, payload: dict[str, Any]) -> None:
        """Publish a push event for a user (best-effort)."""
        if self.redis is None:
            return
        channel = self._channel_for_user(user_id)
        # NOTE: Redis pubsub payload must be bytes/str
        await self.redis.publish(channel, json.dumps(payload, default=str))

    async def publish_inapp_from_row(self, *, row: InAppNotification) -> None:
        """Convenience helper: publish using the persisted inbox row."""
        await self.publish_inapp(
            user_id=row.user_id,
            payload={
                "type": "notification.inapp.created",
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


# NotificationInboxService
class NotificationInboxService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        realtime: NotificationRealtimeService | None = None,
    ):
        self.session = session
        self.realtime = realtime

    async def list_inbox(
        self,
        *,
        user_id: UUID,
        home_id: UUID | None = None,
        unread_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[InAppNotificationOut]:
        stmt = sa.select(InAppNotification).where(InAppNotification.user_id == user_id)

        if home_id is not None:
            stmt = stmt.where(InAppNotification.home_id == home_id)
        if unread_only:
            stmt = stmt.where(InAppNotification.read_at.is_(None))

        stmt = (
            stmt.order_by(InAppNotification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        rows = (await self.session.scalars(stmt)).all()

        return [
            InAppNotificationOut(
                id=r.id,
                event_id=r.event_id,
                home_id=r.home_id,
                subject=r.subject,
                message=r.message,
                read_at=r.read_at,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def unread_count(self, *, user_id: UUID, home_id: UUID | None = None) -> int:
        stmt = (
            sa.select(sa.func.count())
            .select_from(InAppNotification)
            .where(
                InAppNotification.user_id == user_id,
                InAppNotification.read_at.is_(None),
            )
        )

        if home_id is not None:
            stmt = stmt.where(InAppNotification.home_id == home_id)

        count = await self.session.scalar(stmt)
        return int(count or 0)

    async def mark_read(self, *, user_id: UUID, notification_id: UUID) -> bool:
        now = datetime.now(timezone.utc)
        stmt = (
            sa.update(InAppNotification)
            .where(InAppNotification.id == notification_id)
            .where(InAppNotification.user_id == user_id)
            .values(read_at=now, updated_at=now)
            .returning(InAppNotification.id)
        )
        updated_id = await self.session.scalar(stmt)
        # NOTE: no real-time push for mark_read yet (optional).
        return updated_id is not None
