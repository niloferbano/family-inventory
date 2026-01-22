from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.apis.notifications.brokers import EventBroker, LogBroker
from app.apis.notifications.models import NotificationEvent
from app.apis.notifications.schema import (NotificationDeliveryResult,
                                           NotificationRequest,
                                           NotificationResponse)
from app.core.database.exceptions import DomainConflictError


class NotificationService:
    def __init__(self, session, broker: EventBroker | None = None):
        self.session = session
        self.broker = broker or LogBroker()

    async def send(self, req: NotificationRequest) -> NotificationResponse:
        event_id: UUID = req.event_id or uuid4()

        event = NotificationEvent(
            event_id=event_id,
            source=req.source,
            event_type=req.event_type,
            subject=req.subject,
            message=req.message,
            recipients=[
                {
                    "channel": r.channel.value,
                    "recipient": r.recipient,
                    "metadata": r.metadata or {},
                }
                for r in req.recipients
            ],
        )

        # ✅ SAVEPOINT: if this fails, only the savepoint is rolled back, not the outer tx
        try:
            async with self.session.begin_nested():  # SAVEPOINT
                self.session.add(event)
                await self.session.flush()
        except IntegrityError as exc:
            raise DomainConflictError(
                code="NOTIFICATION_EVENT_DUPLICATE",
                message="Notification event already exists (idempotent replay).",
                details={"event_id": str(event_id)},
            ) from exc

        # Publish (note: see outbox note below)
        message = {
            "event_id": str(event_id),
            "source": req.source,
            "event_type": req.event_type,
            "subject": req.subject,
            "message": req.message,
            "recipients": event.recipients,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.broker.publish(message)

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
