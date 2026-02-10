from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.notifications.models import (NotificationDelivery,
                                           NotificationEvent)
from app.apis.notifications.services.ingest import NotificationIngestService
from app.apis.notifications.services.realtime import \
    NotificationRealtimeService
from app.apis.notifications.types import (DeliveryStatus, NotificationChannel,
                                          NotificationRecipientType)
from app.apis.notifications.worker.channels import ChannelSender
from app.core.database.base import NotificationEventId

_realtime_service: NotificationRealtimeService | None = None


def _get_realtime_service() -> NotificationRealtimeService | None:
    """Return a lazily-initialized realtime service.

    We keep this lazy so importing the worker/handlers module doesn't require
    Redis to be available (e.g., during migrations/tests or when realtime push
    is disabled).
    """
    global _realtime_service
    if _realtime_service is not None:
        return _realtime_service

    try:
        # Import here to avoid Redis client initialization at module import time.
        from app.core.redis.client import redis_client  # local import

        _realtime_service = NotificationRealtimeService(redis_client)
        return _realtime_service
    except Exception:
        # If Redis isn't configured/available, realtime is simply disabled.
        return None


LEASE_SECONDS = 120


@dataclass(frozen=True)
class ClaimedDelivery:
    id: UUID
    channel: NotificationChannel
    recipient_type: NotificationRecipientType | None
    recipient: str
    attempt_count: int
    max_attempts: int
    status: DeliveryStatus
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class EventWorkBatch:
    """The full context needed for a processing run."""

    event_id: UUID
    subject: str | None
    message: str
    tasks: list[ClaimedDelivery]


@dataclass(frozen=True)
class DeliverySendResult:
    delivery_id: UUID
    status: DeliveryStatus  # SENT or FAILED
    last_error: str | None = None
    next_retry_at: datetime | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _next_retry_at(attempt_count: int) -> datetime:
    # basic exponential backoff: 1,2,4,8,16 mins (cap at 60 mins)
    minutes = min(60, 2 ** max(0, attempt_count - 1))
    return _utcnow() + timedelta(minutes=minutes)


def _subject_for(topic: str, payload: dict[str, Any]) -> str | None:
    name = payload.get("item_name", "Item")
    if topic == "inventory.item.expired":
        return f"Expired: {name}"
    if topic == "inventory.item.expiring_soon":
        return f"Expiring soon: {name}"
    return payload.get("subject")


def _message_for(topic: str, payload: dict[str, Any]) -> str:
    name = payload.get("item_name", "Item")
    expiry = payload.get("expiry_date")
    if topic == "inventory.item.expired":
        return f"'{name}' is expired (expiry_date={expiry})."
    if topic == "inventory.item.expiring_soon":
        days_left = payload.get("days_left")
        return (
            f"'{name}' is expiring soon (expiry_date={expiry}, days_left={days_left})."
        )
    # fallback for other topics
    return payload.get("message") or f"Event received: {topic}"


def _parse_event_id(payload: dict[str, Any], headers: dict[str, Any]) -> UUID:
    # Prefer payload.event_id, fallback to AMQP message_id/correlation_id if you passed them into headers
    raw = (
        payload.get("event_id")
        or headers.get("message_id")
        or headers.get("correlation_id")
    )
    if not raw:
        raise ValueError(
            "Missing event_id (payload.event_id or headers.message_id/correlation_id)"
        )
    return UUID(str(raw))


async def ensure_event_exists(
    session: AsyncSession,
    *,
    event_id: UUID,
    topic: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
) -> NotificationEvent:
    existing_event = await session.get(NotificationEvent, event_id)
    if existing_event:
        return existing_event

    event = NotificationEvent(
        id=event_id,
        source=str(headers.get("source") or payload.get("source") or "unknown"),
        event_type=topic,  # routing key is your event type
        subject=_subject_for(topic, payload),
        message=_message_for(topic, payload),
        recipients={"recipients": payload.get("recipients", [])},  # optional snapshot
    )
    session.add(event)
    await session.flush()
    return event


async def bulk_upsert_deliveries(
    session: AsyncSession,
    *,
    rows: list[dict],
) -> list[UUID]:
    stmt = (
        pg_insert(NotificationDelivery)
        .values(rows)
        .on_conflict_do_update(
            constraint="uq_delivery_per_target",
            set_={"updated_at": _utcnow()},
        )
        .returning(NotificationDelivery.id)
    )
    return list((await session.execute(stmt)).scalars().all())


async def claim_deliveries_to_send(
    session: AsyncSession,
    *,
    event_id: NotificationEventId,
    now: datetime,
    worker_id: str,
    claim_limit: int = 1000,
) -> list[NotificationDelivery]:
    lease_until = now + timedelta(seconds=LEASE_SECONDS)
    claimable = (
        sa.select(NotificationDelivery.id)
        .where(NotificationDelivery.event_id == event_id)
        .where(NotificationDelivery.attempt_count < NotificationDelivery.max_attempts)
        .where(
            sa.or_(
                NotificationDelivery.status == DeliveryStatus.PENDING,
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
                    NotificationDelivery.lock_expires_at < now,  # stale lease
                ),
            )
        )
        .order_by(NotificationDelivery.created_at.asc())
        .limit(claim_limit)
        .with_for_update(skip_locked=True)
        .subquery()
    )
    stmt = (
        sa.update(NotificationDelivery)
        .where(NotificationDelivery.id.in_(sa.select(claimable.c.id)))
        .values(
            status=DeliveryStatus.SENDING,
            locked_by=worker_id,
            locked_at=now,
            lock_expires_at=lease_until,
            last_attempt_at=now,
            attempt_count=NotificationDelivery.attempt_count + 1,
        )
        .returning(NotificationDelivery)
    )

    res = await session.execute(stmt)
    return list(res.scalars().all())


async def prepare_event_deliveries(
    session: AsyncSession,
    *,
    topic: str,
    payload: dict[str, Any],
    headers: dict[str, Any],
    claim_limit: int = 1000,
    worker_id: str,
) -> EventWorkBatch:
    event_id = _parse_event_id(payload, headers)
    now = _utcnow()

    # Normalize headers first so downstream code (ingest + channel senders) sees a stable shape.
    headers = dict(headers)

    # Preserve original routing key on retry-return messages, otherwise use current topic.
    orig_rk = (
        headers.get("x-original-routing-key")
        or headers.get("x-original-topic")
        or topic
    )
    headers.setdefault("x-original-routing-key", orig_rk)
    headers.setdefault("x-original-topic", orig_rk)

    # Ensure commonly-used routing/topic keys exist.
    headers.setdefault("topic", topic)
    headers.setdefault("routing_key", topic)

    # Ensure we always have event id / home id present in headers for in-app sender and auditing.
    headers.setdefault("event_id", str(payload.get("event_id") or event_id))
    if headers.get("x-event-id") is None:
        # Keep x-event-id in sync when available.
        headers["x-event-id"] = headers["event_id"]

    home_id = (
        payload.get("home_id") or headers.get("home_id") or headers.get("x-home-id")
    )
    if home_id is not None:
        headers.setdefault("home_id", str(home_id))
        headers.setdefault("x-home-id", str(home_id))

    # Build a generic delivery context blob that can be persisted alongside NotificationDelivery.
    # Keep it NotificationEvent-agnostic so non-inventory notifications can reuse it.
    context: dict[str, Any] = {
        "topic": topic,
        "routing_key": topic,
        "x_original_routing_key": headers.get("x-original-routing-key"),
        "source": headers.get("source") or payload.get("source") or "unknown",
        "event_id": headers.get("event_id"),
        "home_id": headers.get("home_id"),
        "message_id": headers.get("message_id"),
        "correlation_id": headers.get("correlation_id"),
    }

    # Attach context so ingest can persist it (e.g., NotificationDelivery.context)
    # and senders can use it at send-time.
    headers.setdefault("context", context)

    # ✅ Step 1: ingest event -> creates NotificationEvent + NotificationDelivery rows
    ingest = NotificationIngestService(session=session)
    await ingest.handle_inventory_event(topic=topic, payload=payload, headers=headers)

    # subject/message should be owned by notifications layer
    subject = ingest._subject(topic, payload)
    message = ingest._message(topic, payload)

    # ✅ Step 2: claim deliveries from DB (NOT from payload.recipients)
    claimed_rows = await claim_deliveries_to_send(
        session,
        event_id=event_id,
        now=now,
        worker_id=worker_id,
        claim_limit=claim_limit,
    )

    claimed: list[ClaimedDelivery] = [
        ClaimedDelivery(
            id=d.id,
            channel=d.channel,
            recipient_type=d.recipient_type,
            recipient=d.recipient,
            attempt_count=d.attempt_count,
            max_attempts=d.max_attempts,
            status=d.status,
            context=getattr(d, "context", None),
        )
        for d in claimed_rows
    ]

    return EventWorkBatch(
        event_id=event_id, subject=subject, message=message, tasks=claimed
    )


async def send_claimed_deliveries(
    *,
    claimed: list[ClaimedDelivery],
    subject: str,
    message: str,
    headers: Mapping[str, Any],
    senders: dict[NotificationChannel, ChannelSender],
    concurrency: int = 50,
) -> list[DeliverySendResult]:
    """
    NO DB:
    Send concurrently with limit. Return per-delivery results.
    """
    # Normalize/ensure topic headers so senders (especially In-App) can rely on them.
    # We see retry-return and envelope formats in the wild, so accept multiple keys.
    base_headers = dict(headers)
    topic = (
        base_headers.get("topic")
        or base_headers.get("routing_key")
        or base_headers.get("x-original-topic")
        or base_headers.get("x-original-routing-key")
        or ""
    )
    if topic:
        base_headers.setdefault("topic", topic)
        base_headers.setdefault("routing_key", topic)
        base_headers.setdefault("x-original-topic", topic)
        base_headers.setdefault("x-original-routing-key", topic)
    sem = asyncio.Semaphore(concurrency)

    async def _send_one(d: ClaimedDelivery) -> DeliverySendResult:
        sender = senders.get(d.channel)
        if not sender:
            return DeliverySendResult(
                delivery_id=d.id,
                status=DeliveryStatus.FAILED,
                last_error=f"Unsupported channel: {d.channel.value}",
                next_retry_at=None,
            )

        async with sem:
            try:
                merged_headers = dict(base_headers)
                # If the delivery row has persisted context (JSONB), merge it.
                # This is how senders (e.g. InAppSender) can reliably see event_id/home_id/topic
                # even when the worker message headers are sparse.
                if d.context and isinstance(d.context, dict):
                    merged_headers.update(d.context)

                await sender.send(
                    recipient=d.recipient,
                    subject=subject,
                    message=message,
                    headers=merged_headers,
                )
                return DeliverySendResult(
                    delivery_id=d.id,
                    status=DeliveryStatus.SENT,
                    last_error=None,
                    next_retry_at=None,
                )
            except Exception as exc:
                # schedule retry time (worker can still do retry by republishing)
                return DeliverySendResult(
                    delivery_id=d.id,
                    status=DeliveryStatus.FAILED,
                    last_error=f"{type(exc).__name__}: {exc}",
                    next_retry_at=_next_retry_at(d.attempt_count),
                )

    return await asyncio.gather(*[_send_one(d) for d in claimed])


async def finalize_delivery_results(
    session: AsyncSession,
    *,
    worker_id: str,
    results: Iterable[DeliverySendResult],
    now: datetime | None = None,
) -> int:
    now = now or _utcnow()
    results = list(results)
    if not results:
        return 0

    by_id: dict[UUID, DeliverySendResult] = {r.delivery_id: r for r in results}
    ids = list(by_id.keys())

    status_case = sa.case(
        {rid: r.status for rid, r in by_id.items()},
        value=NotificationDelivery.id,
        else_=NotificationDelivery.status,
    )
    last_error_case = sa.case(
        {rid: r.last_error for rid, r in by_id.items()},
        value=NotificationDelivery.id,
        else_=NotificationDelivery.last_error,
    )
    next_retry_case = sa.case(
        {rid: r.next_retry_at for rid, r in by_id.items()},
        value=NotificationDelivery.id,
        else_=NotificationDelivery.next_retry_at,
    )

    stmt = (
        sa.update(NotificationDelivery)
        .where(NotificationDelivery.id.in_(ids))
        .where(NotificationDelivery.locked_by == worker_id)
        .where(NotificationDelivery.status == DeliveryStatus.SENDING)
        .values(
            status=status_case,
            last_error=last_error_case,
            next_retry_at=next_retry_case,
            updated_at=now,
            # clear claim/lock
            locked_by=None,
            lock_expires_at=None,
            locked_at=None,
        )
    )

    res = await session.execute(stmt)
    return int(res.rowcount or 0)


def build_failure_results_for_claimed(
    claimed: Iterable["ClaimedDelivery"],
    exc: BaseException,
) -> list["DeliverySendResult"]:
    """
    If something crashes *after claiming* (or before sending), build results
    that mark all claimed deliveries as FAILED so finalize_delivery_results()
    can release locks + record error.

    - status = FAILED
    - last_error = "<ExcType>: <message>"
    - next_retry_at = computed from each delivery's attempt_count
    """
    err = f"{type(exc).__name__}: {exc}"

    results: list[DeliverySendResult] = []
    for d in claimed:
        results.append(
            DeliverySendResult(
                delivery_id=d.id,
                status=DeliveryStatus.FAILED,
                last_error=err,
                next_retry_at=_next_retry_at(d.attempt_count),
            )
        )
    return results
