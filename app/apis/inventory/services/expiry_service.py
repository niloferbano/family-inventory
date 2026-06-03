from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.inventory.events import InventoryEventFactory
from app.apis.inventory.models import InventoryItem
from app.apis.inventory.repository import InventoryRepository
from app.apis.inventory.types import InventoryAlertType
from app.apis.notifications.brokers import EventBroker, EventEnvelope
from app.apis.notifications.models import NotificationOutbox
from app.core.database.base import NotificationEventId

logger = logging.getLogger(__name__)

EVENT_NAMESPACE = UUID("2b6e6d5f-3f7c-4f34-9f6c-7ab8c2d7c4a1")


@dataclass(frozen=True)
class ExpiryAlertBatch:
    expiring_soon: list[InventoryItem]
    expired: list[InventoryItem]


class InventoryExpiryService:
    def __init__(
        self,
        session: AsyncSession | None,
        *,
        broker: EventBroker,
        factory: InventoryEventFactory | None = None,
    ):
        self.session = session
        self.repo = InventoryRepository(session) if session is not None else None
        self.broker = broker
        self.factory = factory or InventoryEventFactory()

    def _apply_context(
        self,
        *,
        topic: str,
        key: str | None,
        event_id: NotificationEventId,
        item: InventoryItem,
        payload: dict,
        headers: dict,
    ) -> tuple[dict, dict]:
        """Mutate/return payload+headers with consistent context fields."""
        # Ensure payload carries ids (helps consumers that prefer payload fields)
        payload.setdefault("event_id", str(event_id))

        item_home_id = getattr(item, "home_id", None)
        if item_home_id:
            payload.setdefault("home_id", str(item_home_id))

        # Normalize headers used across the pipeline
        headers.setdefault("event_id", str(event_id))
        headers.setdefault("x-event-id", str(event_id))
        if key:
            headers.setdefault("x-event-key", str(key))

        if item_home_id:
            headers.setdefault("home_id", str(item_home_id))
            headers.setdefault("x-home-id", str(item_home_id))

        # Routing context (used by workers/senders)
        headers.setdefault("source", "inventory")
        headers.setdefault("topic", str(topic))
        headers.setdefault("routing_key", str(topic))
        headers.setdefault("x-original-routing-key", str(topic))
        headers.setdefault("x-original-topic", str(topic))

        return payload, headers

    def _build_outbox_row(
        self,
        *,
        now: datetime,
        event_id: NotificationEventId,
        topic: str,
        payload: dict,
        headers: dict,
    ) -> dict:
        return {
            "id": uuid.uuid4(),
            "event_id": event_id,
            "topic": str(topic),
            "payload": payload,
            "headers": headers,
            "status": "PENDING",
            "attempt_count": 0,
            "last_error": None,
            "next_retry_at": None,
            "updated_at": now,
        }

    async def publish_expiry_event(
        self,
        *,
        item: InventoryItem,
        alert_type: InventoryAlertType,
        today: date | None = None,
        max_attempts: int = 5,
    ) -> None:
        """Option B: Always write to outbox, then best-effort immediate publish.

        This function *requires* a DB session because Option B persists to NotificationOutbox.

        Note: keep the DB work minimal and avoid row-level lock contention. We:
        - INSERT ... ON CONFLICT DO NOTHING (idempotent)
        - SELECT existing row if it already exists
        - UPDATE ... RETURNING to "claim" a publish attempt (SENDING)

        If you want publish-only behavior with no DB writes, do not use this service
        (or pass a sessionmaker and create a session here).
        """

        if self.session is None:
            raise RuntimeError(
                "InventoryExpiryService.session is None but Option B requires DB writes"
            )

        today = today or date.today()

        envelope = self.factory.expiry_envelope(
            item=item,
            alert_type=alert_type,
            today=today,
        )
        logger.info("expiry_envelope produced: %s", type(envelope))
        if envelope is None:
            logger.warning("expiry_envelope returned None; skipping outbox write")
            return

        # Normalize envelope -> (topic, key, payload, headers)
        topic: str | None = None
        key: str | None = None
        payload: dict = {}
        headers: dict = {}

        if isinstance(envelope, dict):
            topic = envelope.get("topic") or envelope.get("routing_key")
            key = envelope.get("key")
            payload = dict(envelope.get("payload") or {})
            headers = dict(envelope.get("headers") or {})
        else:
            topic = getattr(envelope, "topic", None) or getattr(
                envelope, "routing_key", None
            )
            key = getattr(envelope, "key", None)
            payload = dict(getattr(envelope, "payload", {}) or {})
            headers = dict(getattr(envelope, "headers", {}) or {})

        if not topic:
            raise ValueError("expiry_envelope() must include a topic/routing_key")

        # event_id: producer-provided OR stable derived UUID
        event_id_raw = (
            payload.get("event_id")
            or headers.get("event_id")
            or headers.get("x-event-id")
        )
        if event_id_raw:
            event_id = NotificationEventId(UUID(str(event_id_raw)))
        else:
            stable_key = f"expiry:{item.id}:{alert_type.value}:{today.isoformat()}"
            event_id = NotificationEventId(uuid.uuid5(EVENT_NAMESPACE, stable_key))

        payload, headers = self._apply_context(
            topic=str(topic),
            key=str(key) if key else None,
            event_id=event_id,
            item=item,
            payload=payload,
            headers=headers,
        )

        now = datetime.now(timezone.utc)

        # 1) Ensure an outbox row exists (idempotent by unique event_id)
        # IMPORTANT: avoid ON CONFLICT DO UPDATE here; it can create unnecessary row locks
        # under high concurrency. We'll DO NOTHING then SELECT if needed.
        outbox_row = self._build_outbox_row(
            now=now,
            event_id=event_id,
            topic=str(topic),
            payload=payload,
            headers=headers,
        )

        tbl = NotificationOutbox.__table__
        logger.info(
            "Ensuring outbox row exists for event_id=%s topic=%s", event_id, topic
        )

        insert_stmt = (
            pg_insert(NotificationOutbox)
            .values(outbox_row)
            .on_conflict_do_nothing(index_elements=[tbl.c.event_id])
            .returning(tbl.c.id, tbl.c.status, tbl.c.attempt_count)
        )

        inserted = (await self.session.execute(insert_stmt)).one_or_none()
        if inserted is not None:
            outbox_id, status, attempt_count = inserted
        else:
            existing = (
                await self.session.execute(
                    sa.select(tbl.c.id, tbl.c.status, tbl.c.attempt_count)
                    .where(tbl.c.event_id == event_id)
                    .limit(1)
                )
            ).one_or_none()
            if existing is None:
                # Extremely unlikely (race + rollback). Treat as a retryable error.
                raise RuntimeError(
                    f"Outbox row missing after insert/select for event_id={event_id}"
                )
            outbox_id, status, attempt_count = existing

        # Normalize status in case older rows were written in a different case.
        status_norm = (status or "").upper()

        # If already sent, nothing to do.
        if status_norm == "SENT":
            logger.info(
                "Outbox already SENT; skipping publish. event_id=%s topic=%s",
                event_id,
                topic,
            )
            return

        # Stop if we've exhausted attempts.
        if (attempt_count or 0) >= max_attempts:
            logger.warning(
                "Outbox max_attempts reached; skipping publish. event_id=%s topic=%s attempts=%s",
                event_id,
                topic,
                attempt_count,
            )
            return

        # 2) Claim this outbox row for an immediate publish attempt.
        # This prevents concurrent publishers for the same event.
        claim_stmt = (
            sa.update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .where(sa.func.upper(NotificationOutbox.status).in_(["PENDING", "FAILED"]))
            .where(
                sa.or_(
                    NotificationOutbox.next_retry_at.is_(None),
                    NotificationOutbox.next_retry_at <= now,
                )
            )
            .where(NotificationOutbox.attempt_count < max_attempts)
            .values(
                status="SENDING",
                attempt_count=NotificationOutbox.attempt_count + 1,
                updated_at=now,
            )
            .returning(NotificationOutbox.attempt_count)
        )

        claimed_attempt = (await self.session.execute(claim_stmt)).scalar_one_or_none()
        if claimed_attempt is None:
            # Another worker claimed it or it is not eligible right now.
            # Log current row state to make debugging easier.
            row = (
                await self.session.execute(
                    sa.select(
                        NotificationOutbox.status,
                        NotificationOutbox.attempt_count,
                        NotificationOutbox.next_retry_at,
                    ).where(NotificationOutbox.id == outbox_id)
                )
            ).one_or_none()
            if row is not None:
                cur_status, cur_attempts, cur_next_retry = row
                logger.info(
                    "Outbox claim skipped id=%s event_id=%s status=%s attempts=%s next_retry_at=%s now=%s",
                    outbox_id,
                    event_id,
                    cur_status,
                    cur_attempts,
                    cur_next_retry,
                    now,
                )
            else:
                logger.warning(
                    "Outbox claim skipped id=%s event_id=%s (row not found)",
                    outbox_id,
                    event_id,
                )
            return

        await self.session.flush()

        # 3) Best-effort immediate publish.
        # broker.publish expects an EventEnvelope.
        publish_headers = {k: str(v) for k, v in (headers or {}).items()}
        publish_envelope = EventEnvelope(
            topic=str(topic),
            key=str(key) if key else None,
            payload=payload,
            headers=publish_headers,
        )

        try:
            await self.broker.publish(publish_envelope)
        except Exception as exc:
            logger.warning(
                "Outbox stored but immediate publish failed (dispatcher will retry). event_id=%s topic=%s err=%s",
                event_id,
                topic,
                exc,
            )
            await self.session.execute(
                sa.update(NotificationOutbox)
                .where(NotificationOutbox.id == outbox_id)
                .values(
                    status="FAILED",
                    last_error=f"{type(exc).__name__}: {exc}",
                    next_retry_at=now + timedelta(seconds=60),
                    updated_at=now,
                )
            )
            return

        # 4) Mark SENT
        await self.session.execute(
            sa.update(NotificationOutbox)
            .where(NotificationOutbox.id == outbox_id)
            .values(
                status="SENT",
                last_error=None,
                next_retry_at=None,
                updated_at=now,
            )
        )
