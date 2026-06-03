from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.brokers import EventBroker, EventEnvelope
from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent,
                                           NotificationOutbox)
from app.apis.notifications.types import DeliveryStatus, NotificationChannel
from app.apis.notifications.worker.channels import ChannelSender
from app.apis.notifications.worker.handlers import (
    ClaimedDelivery, build_failure_results_for_claimed,
    claim_deliveries_to_send, finalize_delivery_results,
    send_claimed_deliveries)
from app.core.database.base import NotificationEventId
from app.core.database.session import session_scope

logger = logging.getLogger(__name__)

DEFAULT_SWEEP_INTERVAL_S = 30
DEFAULT_MAX_EVENTS = 100
DEFAULT_CLAIM_LIMIT = 500
DEFAULT_OUTBOX_LIMIT = 200
DEFAULT_MAX_ATTEMPTS = 5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _claim_outbox_rows_for_send(
    session: AsyncSession,
    *,
    now: datetime,
    limit: int,
    max_attempts: int,
) -> list[NotificationOutbox]:
    claimable = (
        sa.select(NotificationOutbox.id)
        .where(NotificationOutbox.attempt_count < max_attempts)
        .where(NotificationOutbox.status.in_(["PENDING", "FAILED"]))
        .where(
            sa.or_(
                NotificationOutbox.next_retry_at.is_(None),
                NotificationOutbox.next_retry_at <= now,
            )
        )
        .order_by(NotificationOutbox.created_at.asc(), NotificationOutbox.id.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
        .subquery()
    )

    # Mark as SENDING + bump attempt_count while holding the row locks
    stmt = (
        sa.update(NotificationOutbox)
        .where(NotificationOutbox.id.in_(sa.select(claimable.c.id)))
        .values(
            status="SENDING",
            attempt_count=NotificationOutbox.attempt_count + 1,
            updated_at=now,
        )
        .returning(NotificationOutbox)
    )

    res = await session.execute(stmt)
    return list(res.scalars().all())


async def _fetch_retry_event_ids(
    session: AsyncSession, *, now: datetime, limit: int
) -> list[UUID]:
    stmt = (
        sa.select(NotificationDelivery.event_id)
        .where(NotificationDelivery.attempt_count < NotificationDelivery.max_attempts)
        .where(
            sa.or_(
                sa.and_(
                    NotificationDelivery.status == DeliveryStatus.FAILED,
                    sa.or_(
                        NotificationDelivery.next_retry_at.is_(None),
                        NotificationDelivery.next_retry_at <= now,
                    ),
                ),
                sa.and_(
                    NotificationDelivery.status == DeliveryStatus.SENDING,
                    NotificationDelivery.lock_expires_at.isnot(None),
                    NotificationDelivery.lock_expires_at < now,
                ),
            )
        )
        .order_by(NotificationDelivery.event_id.asc())
        .distinct()
        .limit(limit)
    )
    return list((await session.scalars(stmt)).all())


def _outbox_next_retry_at(attempt_count: int) -> datetime:
    # basic exponential backoff: 1,2,4,8,16 mins (cap at 60 mins)
    minutes = min(60, 2 ** max(0, attempt_count - 1))
    return _utcnow() + timedelta(minutes=minutes)


async def sweep_outbox_once(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    broker: EventBroker,
    limit: int = DEFAULT_OUTBOX_LIMIT,
    max_attempts: int = 5,
) -> int:
    now = _utcnow()

    # 1) Claim rows in a single txn and mark them as SENDING (+ bump attempt_count)
    async with session_scope(sessionmaker) as session:
        async with session.begin():
            rows = await _claim_outbox_rows_for_send(
                session,
                now=now,
                limit=limit,
                max_attempts=max_attempts,
            )

    if not rows:
        return 0

    # 2) Publish outside txn, collect outcomes
    published = 0
    results: dict[UUID, dict[str, Any]] = {}

    for r in rows:
        headers: dict[str, Any] = dict(r.headers or {})

        # ensure stable keys for worker/ingest
        headers.setdefault("event_id", str(r.event_id))
        headers.setdefault("x-event-id", str(r.event_id))
        headers.setdefault("topic", str(r.topic))
        headers.setdefault("routing_key", str(r.topic))
        headers.setdefault("x-original-routing-key", str(r.topic))
        headers.setdefault("x-original-topic", str(r.topic))

        # key is optional; pick best-effort without assuming it exists
        key = headers.get("x-event-key") or headers.get("correlation_id") or None
        key = str(key) if key else None

        envelope = EventEnvelope(
            topic=str(r.topic),
            key=key,
            payload=dict(r.payload or {}),
            headers={k: str(v) for k, v in headers.items() if v is not None},
        )

        try:
            await broker.publish(envelope)
            published += 1
            results[r.id] = {
                "status": "SENT",
                "last_error": None,
                "next_retry_at": None,
            }
        except Exception as exc:
            logger.exception(
                "Outbox publish failed id=%s event_id=%s", r.id, r.event_id
            )
            results[r.id] = {
                "status": "FAILED",
                "last_error": f"{type(exc).__name__}: {exc}",
                "next_retry_at": _outbox_next_retry_at(r.attempt_count),
            }

    # 3) Finalize all rows in ONE bulk UPDATE
    ids = list(results.keys())

    status_case = sa.case(
        {rid: results[rid]["status"] for rid in ids},
        value=NotificationOutbox.id,
        else_=NotificationOutbox.status,
    )
    last_error_case = sa.case(
        {rid: results[rid]["last_error"] for rid in ids},
        value=NotificationOutbox.id,
        else_=NotificationOutbox.last_error,
    )
    next_retry_case = sa.case(
        {rid: results[rid]["next_retry_at"] for rid in ids},
        value=NotificationOutbox.id,
        else_=NotificationOutbox.next_retry_at,
    )

    async with session_scope(sessionmaker) as session:
        async with session.begin():
            await session.execute(
                sa.update(NotificationOutbox)
                .where(NotificationOutbox.id.in_(ids))
                .values(
                    status=status_case,
                    last_error=last_error_case,
                    next_retry_at=next_retry_case,
                    updated_at=_utcnow(),
                )
            )

    return published


async def sweep_once(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    senders: dict[NotificationChannel, ChannelSender],
    worker_id: str,
    max_events: int = DEFAULT_MAX_EVENTS,
    claim_limit: int = DEFAULT_CLAIM_LIMIT,
) -> int:
    now = _utcnow()

    # 1) find event_ids that have something retryable
    async with session_scope(sessionmaker) as session:
        async with session.begin():
            event_ids = await _fetch_retry_event_ids(session, now=now, limit=max_events)

    if not event_ids:
        return 0

    processed = 0

    # 2) per-event: claim -> send -> finalize
    for event_id in event_ids:
        # Load event + claim rows in one txn, AND copy subject/message safely
        async with session_scope(sessionmaker) as session:
            async with session.begin():
                event = await session.get(NotificationEvent, event_id)
                if not event:
                    logger.warning("Sweeper missing event_id=%s", event_id)
                    continue

                subject = event.subject
                message = event.message

                base_headers: dict[str, Any] = {
                    "event_id": str(event_id),
                    "x-event-id": str(event_id),
                    "topic": getattr(event, "event_type", None) or "unknown",
                    "routing_key": getattr(event, "event_type", None) or "unknown",
                    "x-original-routing-key": getattr(event, "event_type", None)
                    or "unknown",
                    "source": getattr(event, "source", None) or "unknown",
                }

                claimed = await claim_deliveries_to_send(
                    session,
                    event_id=NotificationEventId(event_id),
                    now=_utcnow(),
                    worker_id=worker_id,
                    claim_limit=claim_limit,
                )

        if not claimed:
            continue

        claimed_rows = [
            ClaimedDelivery(
                id=d.id,
                channel=d.channel,
                recipient_type=d.recipient_type,
                recipient=d.recipient,
                attempt_count=d.attempt_count,
                max_attempts=d.max_attempts,
                status=d.status,
            )
            for d in claimed
        ]

        # IN_APP/PUSH should not be retried via NotificationDelivery; if they exist here
        # (due to earlier schema/ingest changes), mark them as sent to prevent infinite loops.
        non_inapp: list[ClaimedDelivery] = []
        skipped_results = []
        for d in claimed_rows:
            if d.channel in (NotificationChannel.IN_APP, NotificationChannel.PUSH):
                skipped_results.append(
                    build_failure_results_for_claimed(
                        [d],
                        ValueError(
                            f"Delivery channel {d.channel.value} should not be in notification_deliveries"
                        ),
                    )[0]
                )
            else:
                non_inapp.append(d)

        claimed_rows = non_inapp

        send_exc: Exception | None = None
        try:
            results = []
            if claimed_rows:
                results = await send_claimed_deliveries(
                    claimed=claimed_rows,
                    subject=subject or "",
                    message=message,
                    headers=base_headers,
                    senders=senders,
                    concurrency=50,
                )
            # include skipped IN_APP/PUSH results so locks are released and status recorded
            if skipped_results:
                results.extend(skipped_results)
        except Exception as exc:
            send_exc = exc
            results = build_failure_results_for_claimed(claimed_rows, exc)

        async with session_scope(sessionmaker) as session:
            async with session.begin():
                await finalize_delivery_results(
                    session, worker_id=worker_id, results=results
                )

        if send_exc:
            logger.exception(
                "Sweeper send failure (event_id=%s): %s", event_id, send_exc
            )

        processed += 1

    return processed


async def run_sweeper_loop(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    senders: dict[NotificationChannel, ChannelSender],
    worker_id: str,
    broker: EventBroker | None = None,
    interval_s: int = DEFAULT_SWEEP_INTERVAL_S,
) -> None:
    while True:
        try:
            processed = await sweep_once(
                sessionmaker=sessionmaker,
                senders=senders,
                worker_id=worker_id,
            )

            # Only attempt outbox publishing when we actually processed something.
            # This prevents constant DB polling when the system is idle.
            if processed:
                logger.info("Sweeper processed %d delivery event(s)", processed)

                if broker is not None:
                    outbox_sent = await sweep_outbox_once(
                        sessionmaker=sessionmaker,
                        broker=broker,
                    )
                    if outbox_sent:
                        logger.info(
                            "Sweeper published %d outbox message(s)", outbox_sent
                        )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Sweeper loop error")

        await asyncio.sleep(interval_s)
