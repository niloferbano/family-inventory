from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import aio_pika


@dataclass(frozen=True)
class EventEnvelope:
    topic: str  # or routing_key
    key: str | None  # optional partitioning/dedup key
    payload: Mapping[str, Any]  # JSON-serializable
    headers: Mapping[str, str] | None = None


class EventBroker(Protocol):
    async def publish(self, event: EventEnvelope) -> None: ...


logger = logging.getLogger(__name__)


class LogBroker(EventBroker):
    async def connect(self) -> None:
        return

    async def close(self) -> None:
        return

    async def publish(self, event: EventEnvelope) -> None:
        logger.info(
            "[EVENT] topic=%s headers=%s payload=%s",
            event.topic,
            event.headers,
            event.payload,
        )


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

        # topic exchange works well for event routing
        self._exchange = await self._channel.declare_exchange(
            self.exchange_name,
            aio_pika.ExchangeType.TOPIC,
            durable=self.durable,
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

        body = json.dumps(
            {"payload": event.payload, "headers": event.headers or {}},
            default=str,
        ).encode()

        msg = aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            headers=dict(event.headers or {}),
        )
        await self._exchange.publish(msg, routing_key=event.topic)
