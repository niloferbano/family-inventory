from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aio_pika

logger = logging.getLogger(__name__)

EXCHANGE = "notifications"  # must match your settings
QUEUE = "notifications.worker"  # worker queue
BINDINGS = [
    "inventory.item.*",  # consumes inventory expiry events
]


async def main(amqp_url: str) -> None:
    connection = await aio_pika.connect_robust(amqp_url)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=50)

    exchange = await channel.declare_exchange(
        EXCHANGE,
        aio_pika.ExchangeType.TOPIC,
        durable=True,
    )

    queue = await channel.declare_queue(
        QUEUE,
        durable=True,
    )

    for pattern in BINDINGS:
        await queue.bind(exchange, routing_key=pattern)

    logger.info("Worker started. queue=%s bindings=%s", QUEUE, BINDINGS)

    async with queue.iterator() as q:
        async for message in q:
            async with message.process(
                requeue=False
            ):  # ack on success, reject on exception
                routing_key = message.routing_key
                body = message.body.decode("utf-8")

                data: dict[str, Any] = json.loads(body)
                payload = data.get("payload")
                headers = data.get("headers") or {}

                logger.info(
                    "RECV topic=%s headers=%s payload=%s",
                    routing_key,
                    headers,
                    payload,
                )

    await connection.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main("amqp://guest:guest@localhost:5672/"))
