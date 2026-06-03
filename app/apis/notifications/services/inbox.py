from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa

from app.apis.notifications.services.realtime import \
    NotificationRealtimeService

try:
    from redis.asyncio import Redis  # redis-py >= 4
except Exception:  # pragma: no cover
    Redis = None  # type: ignore

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import InAppNotification
from app.apis.notifications.schema import InAppNotificationOut
from app.core.database.base import HomeId, NotificationEventId


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
                event_id=NotificationEventId(r.event_id),
                home_id=HomeId(r.home_id),
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
