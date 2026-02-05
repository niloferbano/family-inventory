from __future__ import annotations

import asyncio
import json
import socket
import uuid
from dataclasses import dataclass

import aio_pika
from aio_pika import IncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.exceptions import UnprocessableMessageError
from app.apis.notifications.types import NotificationChannel
from app.apis.notifications.worker.channels import (ChannelSender, InAppSender,
                                                    LogSender)
from app.apis.notifications.worker.handlers import (
    build_failure_results_for_claimed, finalize_delivery_results,
    prepare_event_deliveries, send_claimed_deliveries)
from app.core.logging import get_logger

logger = get_logger(__name__)


## NOTES : Move worker config to env/config later
def _is_unprocessable(exc: BaseException) -> bool:
    # obvious permanent categories
    if isinstance(exc, (UnprocessableMessageError, ValueError, TypeError)):
        return True

    # schema mismatch / migration issues
    msg = str(exc)
    if "UndefinedColumnError" in msg or "UndefinedTableError" in msg:
        return True
    if "invalid input value for enum" in msg:
        return True

    return False


@dataclass
class WorkerConfig:
    amqp_url: str
    exchange_name: str
    queue_name: str
    bindings: list[str]

    dlx_name: str = "notifications.dlx"
    dlq_name: str = "notifications.dlq"
    dlq_routing_key: str = "dlq"

    retry_exchange_name: str = "notifications.retry"
    retry_rk_30s: str = "retry.30s"
    retry_return_topic: str = "inventory.item.retry"

    prefetch: int = 20
    max_retries: int = 5
    use_broker_retries: bool = True
    worker_concurrency: int = 20


def _get_retry_count(msg: IncomingMessage) -> int:
    v = (msg.headers or {}).get("x-retry-count", 0)
    try:
        return int(v)
    except Exception:
        return 0


class NotificationWorker:
    """
    Notification worker.

    Consumes events from RabbitMQ (topic exchange), creates delivery tasks, sends them via
    configured channel senders, and finalizes delivery state in Postgres.

    Supports broker-managed retries via a retry exchange + TTL retry queues, configured from Settings.
    """

    def __init__(
        self, *, cfg: WorkerConfig, sessionmaker: async_sessionmaker[AsyncSession]
    ):
        self.cfg = cfg
        self.sessionmaker = sessionmaker

        self.worker_id = f"{socket.gethostname()}:{uuid.uuid4().hex[:8]}"

        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.Exchange | None = None
        self._dlx: aio_pika.Exchange | None = None
        self._retry_exchange: aio_pika.Exchange | None = None
        self._queue: aio_pika.Queue | None = None
        self._process_sem = asyncio.Semaphore(self.cfg.worker_concurrency)

        self.senders: dict[NotificationChannel, ChannelSender] = {
            NotificationChannel.LOG: LogSender(),
            NotificationChannel.IN_APP: InAppSender(sessionmaker=sessionmaker),
        }

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self.cfg.amqp_url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=self.cfg.prefetch)

        self._exchange = await self._channel.declare_exchange(
            self.cfg.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        self._dlx = await self._channel.declare_exchange(
            self.cfg.dlx_name,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        self._retry_exchange = await self._channel.declare_exchange(
            self.cfg.retry_exchange_name,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )

        # main queue
        q = await self._channel.declare_queue(self.cfg.queue_name, durable=True)

        for pattern in self.cfg.bindings or []:
            await q.bind(self._exchange, routing_key=pattern)

        await q.bind(self._exchange, routing_key=self.cfg.retry_return_topic)

        dlq = await self._channel.declare_queue(self.cfg.dlq_name, durable=True)
        await dlq.bind(self._dlx, routing_key=self.cfg.dlq_routing_key)

        self._queue = q

    async def connect_with_retry(
        self,
        *,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> None:
        delay = initial_delay
        while True:
            try:
                await self.connect()
                logger.info("Worker connected to RabbitMQ")
                return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception(
                    "RabbitMQ connect failed, retrying in %.1fs: %s", delay, exc
                )
                await asyncio.sleep(delay)
                delay = min(max_delay, delay * 2)

    async def close(self) -> None:
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()

    async def _send_to_dlq(self, msg: IncomingMessage, reason: str) -> None:
        assert self._dlx is not None

        headers = dict(msg.headers or {})
        headers["x-dlq-reason"] = reason
        headers.setdefault("x-original-routing-key", msg.routing_key or "")

        await self._dlx.publish(
            aio_pika.Message(
                body=msg.body,
                headers=headers,
                content_type=msg.content_type or "application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=msg.message_id,
                correlation_id=msg.correlation_id,
            ),
            routing_key=self.cfg.dlq_routing_key,
        )

    async def _publish_retry(
        self,
        *,
        body: bytes,
        headers: dict,
        content_type: str | None,
        message_id: str | None,
        correlation_id: str | None,
    ) -> None:
        assert self._retry_exchange is not None

        await self._retry_exchange.publish(
            aio_pika.Message(
                body=body,
                headers=headers,
                content_type=content_type or "application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=message_id,
                correlation_id=correlation_id,
            ),
            routing_key=self.cfg.retry_rk_30s,
        )

    async def on_message(self, msg: IncomingMessage) -> None:

        async with self._process_sem:
            retry_count = _get_retry_count(msg)

            # Build a stable header map we can pass to downstream code and/or republish.
            amqp_headers = dict(msg.headers or {})
            amqp_headers.setdefault("message_id", msg.message_id)
            amqp_headers.setdefault("correlation_id", msg.correlation_id)

            try:
                raw = json.loads(msg.body.decode("utf-8"))
                payload = raw.get("payload") or raw
                envelope_headers = raw.get("headers") or {}
                headers = {**envelope_headers, **amqp_headers}

                # Prefer original routing key on retry-return messages.
                topic = headers.get("x-original-routing-key") or msg.routing_key or ""
                headers.setdefault("x-original-routing-key", topic)

                # 1) Prepare/claim DB work in a transaction.
                async with self.sessionmaker() as session:
                    async with session.begin():
                        batch = await prepare_event_deliveries(
                            session,
                            topic=topic,
                            payload=payload,
                            headers=headers,
                            claim_limit=1000,
                            worker_id=self.worker_id,
                        )

                event_id, subject, message, claimed = (
                    batch.event_id,
                    batch.subject,
                    batch.message,
                    batch.tasks,
                )

                if not claimed:
                    logger.info("No deliveries to process for event_id=%s", event_id)
                    await msg.ack()
                    return

                # 2) Send outside of a DB transaction.
                send_exc: Exception | None = None
                try:
                    results = await send_claimed_deliveries(
                        claimed=claimed,
                        subject=subject,
                        message=message,
                        headers=headers,
                        senders=self.senders,
                        concurrency=50,
                    )
                except Exception as exc:
                    send_exc = exc
                    results = build_failure_results_for_claimed(claimed, exc)

                # 3) Finalize in DB.
                async with self.sessionmaker() as session:
                    async with session.begin():
                        await finalize_delivery_results(
                            session, worker_id=self.worker_id, results=results
                        )

                if send_exc:
                    raise send_exc

                # Success path.
                await msg.ack()
                return

            except Exception as exc:
                # Permanent failures should be routed directly to the DLQ (no retry).
                if _is_unprocessable(exc):
                    logger.error("Unprocessable message → DLQ: %s", exc)
                    try:
                        await self._send_to_dlq(
                            msg,
                            reason=f"unprocessable_message: {type(exc).__name__}: {exc}",
                        )
                        await msg.ack()
                    except Exception:
                        logger.exception(
                            "Failed to publish unprocessable message to DLQ; requeueing"
                        )
                        await msg.reject(requeue=True)
                    return

                retry_count += 1

                if retry_count > self.cfg.max_retries:
                    logger.exception("DLQ after max retries: %s", exc)
                    try:
                        await self._send_to_dlq(
                            msg,
                            reason=f"max_retries_exceeded: {type(exc).__name__}",
                        )
                        await msg.ack()
                    except Exception:
                        # If DLQ publish fails, requeue the original message.
                        logger.exception("Failed to publish to DLQ; requeueing")
                        await msg.reject(requeue=True)
                    return

                if self.cfg.use_broker_retries:
                    logger.exception(
                        "Retrying via broker (retry=%d): %s", retry_count, exc
                    )
                    # Publish to retry exchange (TTL queue). ACK only after publish succeeds.
                    try:
                        retry_headers = dict(headers)
                        retry_headers.update(
                            {
                                "x-original-routing-key": headers.get(
                                    "x-original-routing-key", msg.routing_key or ""
                                ),
                                "x-retry-count": retry_count,
                            }
                        )

                        await self._publish_retry(
                            body=msg.body,
                            headers=retry_headers,
                            content_type=msg.content_type,
                            message_id=msg.message_id,
                            correlation_id=msg.correlation_id,
                        )
                        await msg.ack()
                    except Exception:
                        logger.exception(
                            "Failed to publish to retry exchange; requeueing"
                        )
                        await msg.reject(requeue=True)
                    return

                # If broker retries are disabled, we currently do not requeue here.
                # Requeue so the message isn't lost.
                logger.exception("Broker retries disabled; requeueing")
                await msg.reject(requeue=True)
                return

    async def run_forever(self) -> None:
        if self._queue is None:
            raise RuntimeError(
                "Worker is not connected. Call connect/connect_with_retry first."
            )
        await self._queue.consume(self.on_message, no_ack=False)
        logger.info("NotificationWorker consuming queue=%s", self.cfg.queue_name)

        # keep process alive
        await asyncio.Future()
