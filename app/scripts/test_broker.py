import asyncio
from dataclasses import dataclass
from typing import Any, Mapping

from app.apis.notifications.brokers import RabbitMQBroker


@dataclass(frozen=True)
class EventEnvelope:
    topic: str
    key: str | None
    payload: Mapping[str, Any]
    headers: Mapping[str, str] | None = None


async def main():
    broker = RabbitMQBroker(
        amqp_url="amqp://guest:guest@localhost:5672/",
        exchange_name="notifications",
    )
    await broker.connect()
    try:
        evt = EventEnvelope(
            topic="inventory.item.expiring_soon",
            key="item-123",
            payload={"item_id": "item-123", "name": "Milk", "days_left": 2},
            headers={"source": "inventory", "home_id": "home-xyz"},
        )
        await broker.publish(evt)  # your broker.publish expects EventEnvelope
        print("✅ Published")
    finally:
        await broker.close()


if __name__ == "__main__":
    asyncio.run(main())
