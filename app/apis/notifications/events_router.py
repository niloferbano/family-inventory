from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query

from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent)
from app.apis.notifications.schema import NotificationEventOut
from app.apis.notifications.types import (NotificationChannel,
                                          NotificationRecipientType)
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/notifications/events", tags=["notifications"])


@router.get("", response_model=list[NotificationEventOut])
async def list_my_notifications(
    limit: int = Query(20, ge=1, le=100),
    since: datetime | None = None,
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        stmt = (
            sa.select(NotificationEvent)
            .join(
                NotificationDelivery,
                NotificationDelivery.event_id == NotificationEvent.id,
            )
            .where(NotificationDelivery.channel == NotificationChannel.PUSH)
            .where(
                NotificationDelivery.recipient_type
                == NotificationRecipientType.IN_APP_USER
            )
            .where(NotificationDelivery.recipient == str(current_user.id))
        )
        if since is not None:
            stmt = stmt.where(NotificationEvent.created_at > since)

        stmt = stmt.order_by(NotificationEvent.created_at.desc()).limit(limit)
        events = list((await session.scalars(stmt)).all())

    return [
        NotificationEventOut(
            event_id=event.id,
            source=event.source,
            event_type=event.event_type,
            subject=event.subject,
            message=event.message,
            created_at=event.created_at,
        )
        for event in events
    ]
