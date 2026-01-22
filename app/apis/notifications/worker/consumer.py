from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass

import aio_pika
from aio_pika import IncomingMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.types import NotificationChannel
from app.apis.notifications.worker.channels import ChannelSender, LogSender
from app.apis.notifications.worker.handlers import process_event

logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    amqp_url: str
    exchange_name: str = "notifications"
    queue_name: str = "notifications.q"

    bindings: list[str] = None

    dlx_name: str = "notifications.dlx"
    dlq_name: str = "notifications.dlq"
    dlq_routing_key: str = "dlq"

    prefetch: int = 20
    max_retries: int = 5
    base_backoff_s: float = 1.0


def _get_retry_count(msg: IncomingMessage) -> int:
    v = (msg.headers or {}).get("x-retry-count", 0)
    try:
        return int(v)
    except Exception:
        return 0


def _backoff(cfg: WorkerConfig, retry_count: int) -> float:
    return min(60.0, cfg.base_backoff_s * (2 ** max(0, retry_count - 1)))


class NotificationWorker:
    def __init__(
        self, *, cfg: WorkerConfig, sessionmaker: async_sessionmaker[AsyncSession]
    ):
        self.cfg = cfg
        self.sessionmaker = sessionmaker

        self._conn: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.Exchange | None = None
        self._dlx: aio_pika.Exchange | None = None

        # configured senders
        self.senders: dict[NotificationChannel, ChannelSender] = {
            NotificationChannel.LOG: LogSender(),
        }

    async def connect(self) -> None:
        self._conn = await aio_pika.connect_robust(self.cfg.amqp_url)
        self._channel = await self._conn.channel()
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

        # main queue
        q = await self._channel.declare_queue(
            self.cfg.queue_name,
            durable=True,
        )
        for pattern in self.cfg.bindings or []:
            await q.bind(self._exchange, routing_key=pattern)

        # DLQ
        dlq = await self._channel.declare_queue(
            self.cfg.dlq_name,
            durable=True,
        )
        await dlq.bind(self._dlx, routing_key=self.cfg.dlq_routing_key)

        self._queue = q

    async def close(self) -> None:
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._conn and not self._conn.is_closed:
            await self._conn.close()

    async def _send_to_dlq(self, msg: IncomingMessage, reason: str) -> None:
        assert self._dlx is not None
        headers = dict(msg.headers or {})
        headers["x-dlq-reason"] = reason
        headers["x-original-routing-key"] = msg.routing_key

        await self._dlx.publish(
            aio_pika.Message(
                body=msg.body,
                headers=headers,
                content_type=msg.content_type,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=self.cfg.dlq_routing_key,
        )

    async def _republish_with_retry(
        self, msg: IncomingMessage, retry_count: int
    ) -> None:
        assert self._exchange is not None
        headers = dict(msg.headers or {})
        headers["x-retry-count"] = retry_count

        await self._exchange.publish(
            aio_pika.Message(
                body=msg.body,
                headers=headers,
                content_type=msg.content_type,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=msg.routing_key or self.cfg.routing_key,
        )

    async def on_message(self, msg: IncomingMessage) -> None:
        retry_count = _get_retry_count(msg)

        async with msg.process(requeue=False):
            try:
                raw = json.loads(msg.body.decode("utf-8"))
                payload = raw.get("payload") or raw  # tolerate both shapes

                # Each message gets its own DB session/transaction
                async with self.sessionmaker() as session:
                    async with session.begin():
                        await process_event(
                            session, payload=payload, senders=self.senders
                        )

            except Exception as exc:
                retry_count += 1
                if retry_count > self.cfg.max_retries:
                    logger.exception("DLQ after max retries: %s", exc)
                    await self._send_to_dlq(
                        msg, reason=f"max_retries_exceeded: {type(exc).__name__}"
                    )
                    return

                delay = _backoff(self.cfg, retry_count)
                logger.exception(
                    "Retrying in %.1fs (retry=%d): %s", delay, retry_count, exc
                )

                # simple delay then republish
                await asyncio.sleep(delay)
                await self._republish_with_retry(msg, retry_count=retry_count)

    async def run_forever(self) -> None:
        assert hasattr(self, "_queue")
        await self._queue.consume(self.on_message, no_ack=False)
        logger.info("NotificationWorker consuming queue=%s", self.cfg.queue_name)

        # keep process alive
        await asyncio.Future()
