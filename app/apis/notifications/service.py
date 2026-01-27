# app/apis/notifications/service.py
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.exc import IntegrityError

from app.apis.notifications.models import NotificationEvent, NotificationOutbox
from app.apis.notifications.schema import (NotificationDeliveryResult,
                                           NotificationRequest,
                                           NotificationResponse)
from app.core.database.exceptions import DomainConflictError


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
                code="NOTIFICATION_EVENT_DUPLICATE",
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
