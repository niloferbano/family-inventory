from __future__ import annotations

import asyncio
import json
import socket
import uuid
from dataclasses import dataclass

import aio_pika
from aio_pika import IncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.types import NotificationChannel
from app.apis.notifications.worker.channels import ChannelSender, LogSender
from app.apis.notifications.worker.handlers import (
    build_failure_results_for_claimed, finalize_delivery_results,
    prepare_event_deliveries, send_claimed_deliveries)
from app.core.logging import get_logger

logger = get_logger(__name__)

## NOTES : Move worker config to env/config later


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

        # configured senders
        self.senders: dict[NotificationChannel, ChannelSender] = {
            NotificationChannel.LOG: LogSender(),
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
        if self._conn and not self._conn.is_closed:
            await self._conn.close()

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

    async def _publish_to_retry_queue(
        self, msg: IncomingMessage, *, retry_count: int
    ) -> None:
        assert self._retry_exchange is not None

        headers = dict(msg.headers or {})
        headers["x-retry-count"] = retry_count
        headers.setdefault("x-original-routing-key", msg.routing_key or "")

        await self._retry_exchange.publish(
            aio_pika.Message(
                body=msg.body,
                headers=headers,
                content_type=msg.content_type or "application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=msg.message_id,
                correlation_id=msg.correlation_id,
            ),
            routing_key=self.cfg.retry_rk_30s,  # "retry.30s"
        )

    async def on_message(self, msg: IncomingMessage) -> None:
        retry_count = _get_retry_count(msg)

        async with msg.process(requeue=False):
            try:
                raw = json.loads(msg.body.decode("utf-8"))
                payload = raw.get("payload") or raw

                envelope_headers = raw.get("headers") or {}
                amqp_headers = dict(msg.headers or {})
                headers = {**envelope_headers, **amqp_headers}

                topic = headers.get("x-original-routing-key") or msg.routing_key or ""

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
                            logger.info(
                                "No deliveries to process for event_id=%s", event_id
                            )
                            return
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

                async with self.sessionmaker() as session:
                    async with session.begin():
                        await finalize_delivery_results(
                            session, worker_id=self.worker_id, results=results
                        )
                if send_exc:
                    raise send_exc

            except Exception as exc:
                retry_count += 1

                # IMPORTANT: ensure x-original-topic is preserved for retry-return
                # even if JSON decoding failed
                msg.headers = dict(msg.headers or {})
                msg.headers.setdefault("x-original-topic", msg.routing_key or "")
                msg.headers["x-retry-count"] = retry_count

                if retry_count > self.cfg.max_retries:
                    logger.exception("DLQ after max retries: %s", exc)
                    await self._send_to_dlq(
                        msg,
                        reason=f"max_retries_exceeded: {type(exc).__name__}",
                    )
                    return

                if self.cfg.use_broker_retries:
                    logger.exception(
                        "Retrying via broker (retry=%d): %s", retry_count, exc
                    )
                    await self._publish_to_retry_queue(msg, retry_count=retry_count)
                    return

                # fallback to old logic if feature flag is off
                # delay = _backoff(self.cfg, retry_count)
                # logger.exception(
                #     "Retrying in %.1fs (retry=%d): %s", delay, retry_count, exc
                # )
                # await asyncio.sleep(delay)
                await self._republish_with_retry(msg, retry_count=retry_count)
                return

    async def run_forever(self) -> None:
        assert hasattr(self, "_queue")
        await self._queue.consume(self.on_message, no_ack=False)
        logger.info("NotificationWorker consuming queue=%s", self.cfg.queue_name)

        # keep process alive
        await asyncio.Future()
