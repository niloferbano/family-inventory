# app/apis/notifications/repository.py
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import NotificationSubscription
from app.apis.notifications.types import NotificationChannel
from app.core.database.base import HomeId, UserId


class NotificationSubscriptionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self, subscription: NotificationSubscription
    ) -> NotificationSubscription:
        self.session.add(subscription)
        await self.session.flush()
        return subscription

    async def get(self, *, sub_id) -> NotificationSubscription | None:
        stmt = sa.select(NotificationSubscription).where(
            NotificationSubscription.id == sub_id
        )
        return await self.session.scalar(stmt)

    async def delete(self, subscription: NotificationSubscription) -> None:
        await self.session.delete(subscription)

    async def list_for_user(
        self, *, user_id: UserId, home_id: HomeId | None = None
    ) -> list[NotificationSubscription]:
        stmt = sa.select(NotificationSubscription).where(
            NotificationSubscription.user_id == user_id
        )
        if home_id is not None:
            stmt = stmt.where(NotificationSubscription.home_id == home_id)

        stmt = stmt.order_by(
            NotificationSubscription.home_id.asc(),
            NotificationSubscription.topic.asc(),
            NotificationSubscription.channel.asc(),
        )
        return list((await self.session.scalars(stmt)).all())

    async def upsert_subscription(
        self,
        *,
        home_id: HomeId,
        user_id: UserId,
        topic: str,
        channel: NotificationChannel,
        enabled: bool,
    ) -> NotificationSubscription:
        stmt = (
            pg_insert(NotificationSubscription)
            .values(
                home_id=home_id,
                user_id=user_id,
                topic=topic,
                channel=channel,
                enabled=enabled,
            )
            .on_conflict_do_update(
                constraint="uq_notification_subscription_target",
                set_={"enabled": enabled},
            )
            .returning(NotificationSubscription)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()

    async def list_enabled_for_topic(
        self,
        *,
        home_id: HomeId,
        topic: str,
        user_id: UserId | None = None,
    ) -> list[NotificationSubscription]:
        wildcard = topic.rsplit(".", 1)[0] + ".*" if "." in topic else "*"
        stmt = sa.select(NotificationSubscription).where(
            NotificationSubscription.home_id == home_id,
            NotificationSubscription.topic.in_([topic, wildcard]),
            NotificationSubscription.enabled.is_(True),
        )

        if user_id is not None:
            stmt = stmt.where(NotificationSubscription.user_id == user_id)

        stmt = stmt.order_by(
            NotificationSubscription.user_id.asc(),
            NotificationSubscription.channel.asc(),
        )

        return list((await self.session.scalars(stmt)).all())
