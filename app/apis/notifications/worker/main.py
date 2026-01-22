import asyncio
import logging

from app.apis.notifications.worker.consumer import (NotificationWorker,
                                                    WorkerConfig)
from app.core.configs.config import settings
from app.core.database.session import get_db

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    db = get_db()

    cfg = WorkerConfig(
        amqp_url=settings.RABBITMQ_URL,
        exchange_name=settings.NOTIFICATION_EXCHANGE,
        queue_name=settings.NOTIFICATION_QUEUE,
        routing_key=settings.NOTIFICATION_ROUTING_KEY,  # e.g. "notifications.#"
        dlx_name=settings.NOTIFICATION_DLX,
        dlq_name=settings.NOTIFICATION_DLQ,
    )

    worker = NotificationWorker(cfg=cfg, sessionmaker=db.sessionmaker)

    await worker.connect()
    try:
        await worker.run_forever()
    finally:
        await worker.close()
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
