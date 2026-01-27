# app/apis/notifications/worker/__main__.py
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.worker.consumer import (NotificationWorker,
                                                    WorkerConfig)
from app.core.configs.config import settings
from app.core.database.session import get_db

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    db = get_db()

    # DB sessionmaker for the worker
    sessionmaker: async_sessionmaker[AsyncSession] = db.sessionmaker

    cfg = WorkerConfig(
        amqp_url=settings.RABBITMQ_URL,
        exchange_name=settings.NOTIFICATION_EXCHANGE,  # must match publisher
        queue_name=settings.NOTIFICATION_QUEUE,  # e.g. "notifications.q"
        bindings=[
            "inventory.item.*",  # consume inventory expiry events
            # add more patterns later
        ],
        prefetch=20,
        max_retries=5,
    )

    worker = NotificationWorker(cfg=cfg, sessionmaker=sessionmaker)
    await worker.connect()
    try:
        await worker.run_forever()
    finally:
        await worker.close()
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
