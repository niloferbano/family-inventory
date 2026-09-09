import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.apis.notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationOutbox,
)
from app.apis.notifications.types import (
    DeliveryStatus,
    NotificationChannel,
    NotificationRecipientType,
)
from app.apis.notifications.worker import sweeper


@pytest.mark.asyncio
@pytest.mark.parametrize("fails", [False, True])
async def test_outbox_publishes_committed_claim_and_persists_result(mock_db, fails):
    async with mock_db.begin() as session:
        row = NotificationOutbox(
            event_id=uuid4(),
            topic="inventory.item.expired",
            payload={"item": "milk"},
            headers={"x-event-key": "item-1"},
        )
        session.add(row)
        await session.flush()
        row_id, event_id = row.id, row.event_id

    async def publish(envelope):
        # A separate transaction must see the claim before the external send.
        async with mock_db.begin() as session:
            claimed = await session.get(NotificationOutbox, row_id)
            assert claimed.status == "SENDING"
            assert claimed.attempt_count == 1
        assert envelope.headers["event_id"] == str(event_id)
        assert envelope.key == "item-1"
        assert envelope.payload == {"item": "milk"}
        if fails:
            raise ConnectionError("broker unavailable")

    broker = SimpleNamespace(publish=AsyncMock(side_effect=publish))
    assert await sweeper.sweep_outbox_once(
        sessionmaker=mock_db.sessionmaker, broker=broker
    ) == int(not fails)
    async with mock_db.begin() as session:
        row = await session.get(NotificationOutbox, row_id)
        assert row.status == ("FAILED" if fails else "SENT")
        assert row.attempt_count == 1
        if fails:
            assert "broker unavailable" in row.last_error
            assert row.next_retry_at > datetime.now(timezone.utc)
        else:
            assert row.last_error is None
            assert row.next_retry_at is None
    # Neither a sent row nor a future retry should publish again.
    assert (
        await sweeper.sweep_outbox_once(
            sessionmaker=mock_db.sessionmaker, broker=broker
        )
        == 0
    )
    broker.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_outbox_skips_ineligible_rows(mock_db):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    async with mock_db.begin() as session:
        for status, attempts, retry in [
            ("SENT", 1, None),
            ("SENDING", 1, None),
            ("FAILED", 5, None),
            ("FAILED", 1, future),
        ]:
            session.add(
                NotificationOutbox(
                    event_id=uuid4(),
                    topic="test",
                    payload={},
                    headers={},
                    status=status,
                    attempt_count=attempts,
                    next_retry_at=retry,
                )
            )
    broker = SimpleNamespace(publish=AsyncMock())
    assert (
        await sweeper.sweep_outbox_once(
            sessionmaker=mock_db.sessionmaker, broker=broker
        )
        == 0
    )
    broker.publish.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("stale_lease", [False, True])
@pytest.mark.parametrize("fails", [False, True])
async def test_delivery_retry_reclaims_and_finalizes(mock_db, stale_lease, fails):
    past = datetime.now(timezone.utc) - timedelta(minutes=2)
    async with mock_db.begin() as session:
        event = NotificationEvent(
            source="inventory",
            event_type="inventory.item.expired",
            subject="Expired",
            message="Milk",
            recipients={},
        )
        session.add(event)
        await session.flush()
        delivery = NotificationDelivery(
            event_id=event.id,
            channel=NotificationChannel.EMAIL,
            recipient_type=NotificationRecipientType.EMAIL,
            recipient="test@example.com",
            status=DeliveryStatus.SENDING if stale_lease else DeliveryStatus.FAILED,
            attempt_count=1,
            next_retry_at=past,
            locked_by="dead-worker" if stale_lease else None,
            lock_expires_at=past if stale_lease else None,
        )
        session.add(delivery)
        await session.flush()
        delivery_id = delivery.id
    sender = SimpleNamespace(
        send=AsyncMock(
            side_effect=ConnectionError("smtp unavailable") if fails else None
        )
    )
    assert (
        await sweeper.sweep_once(
            sessionmaker=mock_db.sessionmaker,
            senders={NotificationChannel.EMAIL: sender},
            worker_id="test-worker",
        )
        == 1
    )
    sender.send.assert_awaited_once()
    assert sender.send.call_args.kwargs["recipient"] == "test@example.com"
    async with mock_db.begin() as session:
        delivery = await session.get(NotificationDelivery, delivery_id)
        assert delivery.status == (
            DeliveryStatus.FAILED if fails else DeliveryStatus.SENT
        )
        assert delivery.attempt_count == 2
        assert delivery.locked_by is None
        assert delivery.lock_expires_at is None
        if fails:
            assert "smtp unavailable" in delivery.last_error
            assert delivery.next_retry_at > datetime.now(timezone.utc)
    assert (
        await sweeper.sweep_once(
            sessionmaker=mock_db.sessionmaker,
            senders={NotificationChannel.EMAIL: sender},
            worker_id="test-worker",
        )
        == 0
    )


@pytest.mark.asyncio
async def test_idle_delivery_queue_does_not_block_outbox_dispatch(monkeypatch):
    monkeypatch.setattr(sweeper, "sweep_once", AsyncMock(return_value=0))
    publish = AsyncMock(return_value=1)
    monkeypatch.setattr(sweeper, "sweep_outbox_once", publish)
    monkeypatch.setattr(
        sweeper.asyncio, "sleep", AsyncMock(side_effect=asyncio.CancelledError())
    )
    broker = object()
    with pytest.raises(asyncio.CancelledError):
        await sweeper.run_sweeper_loop(
            sessionmaker=object(), senders={}, worker_id="test", broker=broker
        )
    publish.assert_awaited_once()
    assert publish.call_args.kwargs["broker"] is broker


@pytest.mark.asyncio
async def test_concurrent_outbox_claims_do_not_publish_twice(mock_db):
    async with mock_db.begin() as session:
        session.add(
            NotificationOutbox(event_id=uuid4(), topic="test", payload={}, headers={})
        )
    entered = asyncio.Event()
    release = asyncio.Event()

    async def publish(envelope):
        entered.set()
        await release.wait()

    broker = SimpleNamespace(publish=AsyncMock(side_effect=publish))
    first = asyncio.create_task(
        sweeper.sweep_outbox_once(sessionmaker=mock_db.sessionmaker, broker=broker)
    )
    try:
        await asyncio.wait_for(entered.wait(), 5)
        assert (
            await sweeper.sweep_outbox_once(
                sessionmaker=mock_db.sessionmaker, broker=broker
            )
            == 0
        )
    finally:
        release.set()
        await first
    broker.publish.assert_awaited_once()


@pytest.mark.asyncio
async def test_retry_selection_skips_future_exhausted_and_live_leases(mock_db):
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    async with mock_db.begin() as session:
        event = NotificationEvent(
            source="inventory", event_type="test", message="Milk", recipients={}
        )
        session.add(event)
        await session.flush()
        for i, (status, attempts, retry, lease) in enumerate(
            [
                (DeliveryStatus.FAILED, 1, future, None),
                (DeliveryStatus.FAILED, 5, None, None),
                (DeliveryStatus.SENDING, 1, None, future),
                (DeliveryStatus.SENT, 1, None, None),
            ]
        ):
            session.add(
                NotificationDelivery(
                    event_id=event.id,
                    channel=NotificationChannel.EMAIL,
                    recipient_type=NotificationRecipientType.EMAIL,
                    recipient=f"test{i}@example.com",
                    status=status,
                    attempt_count=attempts,
                    next_retry_at=retry,
                    lock_expires_at=lease,
                )
            )
    sender = SimpleNamespace(send=AsyncMock())
    assert (
        await sweeper.sweep_once(
            sessionmaker=mock_db.sessionmaker,
            senders={NotificationChannel.EMAIL: sender},
            worker_id="test",
        )
        == 0
    )
    sender.send.assert_not_awaited()
