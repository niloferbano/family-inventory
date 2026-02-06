from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import aio_pika

from app.core.configs.config import settings


@dataclass(frozen=True)
class EventEnvelope:
    topic: str  # or routing_key
    key: str | None  # optional partitioning/dedup key
    payload: Mapping[str, Any]  # JSON-serializable
    headers: Mapping[str, str] | None = None


class EventBroker(Protocol):
    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def publish(self, event: EventEnvelope) -> None: ...


logger = logging.getLogger(__name__)


class LogBroker(EventBroker):
    async def connect(self) -> None:
        logger.infor(
            "LOG BROKER: using LogBroker - events will be logged, not published to a real broker"
        )
        return

    async def close(self) -> None:
        logger.info("LOG BROKER: closing LogBroker (no-op)")
        return

    async def publish(self, event: EventEnvelope) -> None:
        logger.info(
            "[EVENT] topic=%s headers=%s payload=%s",
            event.topic,
            event.headers,
            event.payload,
        )


async def setup_mq_infrastructure(
    channel: aio_pika.RobustChannel,
    *,
    main_exchange_name: str,
    main_queue_name: str,
    bindings: list[str],
    retry_exchange_name: str,
    retry_routing_key: str,
    retry_return_topic: str,
    dlq_name: str,
    dlq_routing_key: str = "fail",
    retry_ttl_ms: int = 30_000,
    retry_queue_suffix: str = "retry_30s",
) -> None:
    """Declare RabbitMQ infra for broker-managed retries.

    Topology (Option B):
      - `main_exchange_name` (TOPIC): normal publish exchange.
      - `main_queue_name` (QUEUE): worker consumes from here.
         * bound to `bindings` (normal topics)
         * also bound to `retry_return_topic` (messages returning from retry TTL)
      - `retry_exchange_name` (DIRECT): worker republishes failed messages here.
      - retry queue (TTL): receives messages on `retry_routing_key`, waits `retry_ttl_ms`,
        then dead-letters back to `main_exchange_name` with routing key `retry_return_topic`.
      - DLQ: receives messages published to `retry_exchange_name` with `dlq_routing_key`.

    IMPORTANT: bindings/topics must come from Settings (do not hard-code).
    NOTE: Queue/exchange declarations must remain consistent across runs; changing arguments
    for an existing queue name will raise PRECONDITION_FAILED.
    """

    # Exchanges
    main_exchange = await channel.declare_exchange(
        name=main_exchange_name,
        type=aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    retry_exchange = await channel.declare_exchange(
        name=retry_exchange_name,
        type=aio_pika.ExchangeType.DIRECT,
        durable=True,
    )

    # Main worker queue
    main_queue = await channel.declare_queue(name=main_queue_name, durable=True)

    # Bind normal topics
    for pattern in bindings:
        p = (pattern or "").strip()
        if not p:
            continue
        await main_queue.bind(exchange=main_exchange, routing_key=p)

    # Messages return here after TTL
    await main_queue.bind(exchange=main_exchange, routing_key=retry_return_topic)

    # Retry queue (TTL) that dead-letters back to the main exchange
    retry_queue_name = f"{main_queue_name}.{retry_queue_suffix}"
    retry_queue = await channel.declare_queue(
        name=retry_queue_name,
        durable=True,
        arguments={
            "x-message-ttl": int(retry_ttl_ms),
            "x-dead-letter-exchange": main_exchange_name,
            "x-dead-letter-routing-key": retry_return_topic,
        },
    )
    await retry_queue.bind(exchange=retry_exchange, routing_key=retry_routing_key)

    # DLQ for terminal failures
    dlq = await channel.declare_queue(name=dlq_name, durable=True)
    await dlq.bind(exchange=retry_exchange, routing_key=dlq_routing_key)


class RabbitMQBroker(EventBroker):
    """
    Reusable publisher:
    - Connect once (startup) via `connect()`
    - Publish via `publish()`
    - Close once (shutdown) via `close()`
    """

    def __init__(
        self,
        amqp_url: str,
        exchange_name: str = "notifications",
        durable: bool = True,
    ):
        self.amqp_url = amqp_url
        self.exchange_name = exchange_name
        self.durable = durable

        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.Exchange | None = None

    async def connect(self) -> None:
        self._connection = await aio_pika.connect_robust(self.amqp_url)
        self._channel = await self._connection.channel(publisher_confirms=True)

        self._exchange = await self._channel.declare_exchange(
            self.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=self.durable,
        )

        await setup_mq_infrastructure(
            self._channel,
            main_exchange_name=settings.NOTIFICATION_EXCHANGE,
            main_queue_name=settings.NOTIFICATION_QUEUE,
            bindings=settings.notification_bindings_list(),
            retry_exchange_name=settings.NOTIFICATION_RETRY_EXCHANGE,
            retry_routing_key=settings.NOTIFICATION_RETRY_ROUTING_KEY_30S,
            retry_return_topic=settings.NOTIFICATION_RETRY_RETURN_TOPIC,
            dlq_name=settings.NOTIFICATION_DLQ,
            dlq_routing_key=getattr(settings, "NOTIFICATION_DLQ_ROUTING_KEY", "fail"),
            retry_ttl_ms=getattr(settings, "NOTIFICATION_RETRY_TTL_MS", 30_000),
            retry_queue_suffix=getattr(
                settings, "NOTIFICATION_RETRY_QUEUE_SUFFIX", "retry_30s"
            ),
        )

    async def close(self) -> None:
        # RobustConnection handles reconnects; close cleanly on shutdown
        if self._channel and not self._channel.is_closed:
            await self._channel.close()
        if self._connection and not self._connection.is_closed:
            await self._connection.close()

        self._exchange = None
        self._channel = None
        self._connection = None

    async def publish(self, event: EventEnvelope) -> None:
        if not self._exchange:
            raise RuntimeError("RabbitMQBroker is not connected. Call connect() first.")

        event_id: str | None = None
        try:
            v = event.payload.get("event_id")
            event_id = str(v) if v else None
        except Exception:
            event_id = None

        message_id = event_id or (str(event.key) if event.key else None)

        correlation_id = str(event.key) if event.key else None

        headers = dict(event.headers or {})
        if event.key:
            headers["x-event-key"] = str(event.key)
        if event_id:
            headers["x-event-id"] = event_id

        body = json.dumps(
            {"payload": event.payload, "headers": headers},
            default=str,
        ).encode("utf-8")

        msg = aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers=headers,
            message_id=message_id,
            correlation_id=correlation_id,
        )
        await self._exchange.publish(msg, routing_key=event.topic)
