import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.apis.notifications.worker import consumer


@pytest.fixture
def worker(mock_db, monkeypatch):
    monkeypatch.setattr(consumer, "_build_realtime_service", lambda: None)
    return consumer.NotificationWorker(
        cfg=consumer.WorkerConfig(
            amqp_url="amqp://unused",
            exchange_name="events",
            queue_name="notifications",
            bindings=["inventory.item.*"],
        ),
        sessionmaker=mock_db.sessionmaker,
    )


def message(body=None, headers=None):
    return SimpleNamespace(
        body=(
            body
            if body is not None
            else json.dumps({"payload": {"event_id": str(uuid4())}}).encode()
        ),
        headers=headers or {},
        routing_key="inventory.item.expired",
        content_type="application/json",
        message_id="message-1",
        correlation_id="item-1",
        ack=AsyncMock(),
        reject=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("has_tasks", [True, False])
async def test_ack_only_after_delivery_finalization(worker, monkeypatch, has_tasks):
    batch = SimpleNamespace(
        event_id=uuid4(),
        subject="Expired",
        message="Milk",
        tasks=["task"] if has_tasks else [],
    )
    prepare = AsyncMock(return_value=batch)
    send = AsyncMock(return_value=["result"])
    msg = message(headers={"x-original-routing-key": "inventory.item.expiring_soon"})

    async def finalize(*args, **kwargs):
        msg.ack.assert_not_awaited()
        assert kwargs["results"] == ["result"]

    finalize_mock = AsyncMock(side_effect=finalize)
    monkeypatch.setattr(consumer, "prepare_event_deliveries", prepare)
    monkeypatch.setattr(consumer, "send_claimed_deliveries", send)
    monkeypatch.setattr(consumer, "finalize_delivery_results", finalize_mock)
    await worker.on_message(msg)
    msg.ack.assert_awaited_once()
    msg.reject.assert_not_awaited()
    assert prepare.call_args.kwargs["topic"] == "inventory.item.expiring_soon"
    assert send.await_count == int(has_tasks)
    assert finalize_mock.await_count == int(has_tasks)


@pytest.mark.asyncio
@pytest.mark.parametrize("publish_fails", [False, True])
@pytest.mark.parametrize("permanent", [False, True])
async def test_dlq_acknowledges_only_after_successful_publish(
    worker, monkeypatch, permanent, publish_fails
):
    worker._dlx = SimpleNamespace(
        publish=AsyncMock(
            side_effect=ConnectionError("broker down") if publish_fails else None
        )
    )
    monkeypatch.setattr(
        consumer,
        "prepare_event_deliveries",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    msg = message(
        body=b"{invalid" if permanent else None,
        headers={"x-retry-count": worker.cfg.max_retries},
    )
    await worker.on_message(msg)
    sent = worker._dlx.publish.call_args.args[0]
    assert sent.body == msg.body
    assert sent.message_id == msg.message_id
    assert (
        "unprocessable_message" if permanent else "max_retries_exceeded"
    ) in sent.headers["x-dlq-reason"]
    assert msg.ack.await_count == int(not publish_fails)
    if publish_fails:
        msg.reject.assert_awaited_once_with(requeue=True)
    else:
        msg.reject.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("publish_fails", [False, True])
async def test_transient_error_preserves_message_and_increments_retry(
    worker, monkeypatch, publish_fails
):
    monkeypatch.setattr(
        consumer,
        "prepare_event_deliveries",
        AsyncMock(side_effect=ConnectionError("database down")),
    )
    worker._retry_exchange = SimpleNamespace(
        publish=AsyncMock(
            side_effect=ConnectionError("broker down") if publish_fails else None
        )
    )
    msg = message(headers={"x-retry-count": 2})
    await worker.on_message(msg)
    sent = worker._retry_exchange.publish.call_args.args[0]
    assert sent.body == msg.body
    assert sent.headers["x-retry-count"] == 3
    assert sent.headers["x-original-routing-key"] == msg.routing_key
    assert sent.correlation_id == msg.correlation_id
    assert msg.ack.await_count == int(not publish_fails)
    if publish_fails:
        msg.reject.assert_awaited_once_with(requeue=True)


@pytest.mark.asyncio
async def test_disabled_broker_retries_requeue(worker, monkeypatch):
    worker.cfg.use_broker_retries = False
    monkeypatch.setattr(
        consumer, "prepare_event_deliveries", AsyncMock(side_effect=ConnectionError())
    )
    msg = message()
    await worker.on_message(msg)
    msg.reject.assert_awaited_once_with(requeue=True)
    msg.ack.assert_not_awaited()


@pytest.mark.asyncio
async def test_connection_retries_with_bounded_backoff_and_propagates_cancellation(
    worker, monkeypatch
):
    worker.connect = AsyncMock(side_effect=[ConnectionError(), ConnectionError(), None])
    sleep = AsyncMock()
    monkeypatch.setattr(consumer.asyncio, "sleep", sleep)
    await worker.connect_with_retry(initial_delay=2, max_delay=3)
    assert [c.args[0] for c in sleep.call_args_list] == [2, 3]
    worker.connect = AsyncMock(side_effect=asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await worker.connect_with_retry()
