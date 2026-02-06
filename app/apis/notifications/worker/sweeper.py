from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent)
from app.apis.notifications.types import DeliveryStatus, NotificationChannel
from app.apis.notifications.worker.channels import ChannelSender
from app.apis.notifications.worker.handlers import (
    ClaimedDelivery, build_failure_results_for_claimed,
    claim_deliveries_to_send, finalize_delivery_results,
    send_claimed_deliveries)
from app.core.database.session import session_scope

logger = logging.getLogger(__name__)

DEFAULT_SWEEP_INTERVAL_S = 30
DEFAULT_MAX_EVENTS = 100
DEFAULT_CLAIM_LIMIT = 500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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

                claimed = await claim_deliveries_to_send(
                    session,
                    event_id=event_id,
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

        send_exc: Exception | None = None
        try:
            results = await send_claimed_deliveries(
                claimed=claimed_rows,
                subject=subject,
                message=message,
                headers={},  # optional
                senders=senders,
                concurrency=50,
            )
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
    interval_s: int = DEFAULT_SWEEP_INTERVAL_S,
) -> None:
    while True:
        try:
            processed = await sweep_once(
                sessionmaker=sessionmaker,
                senders=senders,
                worker_id=worker_id,
            )
            if processed:
                logger.info("Sweeper processed %d event(s)", processed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Sweeper loop error")

        await asyncio.sleep(interval_s)
