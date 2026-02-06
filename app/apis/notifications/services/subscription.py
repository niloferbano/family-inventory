from uuid import UUID

try:
    from redis.asyncio import Redis  # redis-py >= 4
except Exception:  # pragma: no cover
    Redis = None  # type: ignore

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homeuser.repository import HomeUserRepository
from app.apis.notifications.models import NotificationSubscription
from app.apis.notifications.repository import \
    NotificationSubscriptionRepository
from app.apis.notifications.schema import (SubscriptionCreateRequest,
                                           SubscriptionUpdate)
from app.core.database.base import HomeId, UserId
from app.core.database.error_codes import ErrorCode
from app.core.database.exceptions import (DomainConflictError,
                                          DomainNotFoundError,
                                          DomainPermissionError)


class NotificationSubscriptionsService:
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
