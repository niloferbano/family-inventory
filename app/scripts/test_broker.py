import asyncio

from app.apis.notifications.brokers import EventEnvelope, RabbitMQBroker


async def test():
    broker = RabbitMQBroker(
        amqp_url="amqp://guest:guest@localhost/",
        exchange_name="notifications",
    )
    await broker.connect()

    await broker.publish(
        EventEnvelope(
            topic="inventory.item.expired",
            key="test",
            payload={
                "event_id": "11111111-1111-1111-1111-111111111111",
                "home_id": "22222222-2222-2222-2222-222222222222",
                "item_name": "Milk",
                "expiry_date": "2026-01-01",
                "source": "unit_test",
                "event_type": "inventory.item.expired",
                "message": "Your item Milk has expired on 2026-01-01.",
                "recipients": [
                    {
                        "channel": "log",
                        "recipient": "stdout",
                        "recipient_type": "log",
                    }
                ],
            },
            headers={"source": "test"},
        )
    )

    await broker.close()


asyncio.run(test())
