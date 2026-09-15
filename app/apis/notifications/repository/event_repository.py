from uuid import UUID

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import NotificationEvent


class NotificationEventRepository:
    """Access notification events within the caller's transaction; never commit."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, event_id: UUID) -> NotificationEvent | None:
        return await self.session.get(NotificationEvent, event_id)

    async def create(self, event: NotificationEvent) -> NotificationEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_if_missing(
        self,
        *,
        event_id: UUID,
        source: str,
        event_type: str,
        subject: str | None,
        message: str,
        recipients: dict,
    ) -> None:
        """Insert without changing an existing event when its ID is redelivered."""
        await self.session.execute(
            pg_insert(NotificationEvent)
            .values(
                id=event_id,
                source=source,
                event_type=event_type,
                subject=subject,
                message=message,
                recipients=recipients,
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
