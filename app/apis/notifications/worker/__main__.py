from __future__ import annotations

import asyncio
import contextlib
import signal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.worker.consumer import (NotificationWorker,
                                                    WorkerConfig)
from app.apis.notifications.worker.sweeper import run_sweeper_loop
from app.core.configs.config import settings
from app.core.database.session import get_db


async def main() -> None:
    db = get_db()
    # Ensure the DB engine/pool is initialized for standalone worker runs.
    await db.connect()

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

    shutdown = asyncio.Event()

    def _request_shutdown() -> None:
        shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_shutdown)

    async def _run_worker() -> None:
        # Run until we are asked to shut down.
        worker_task = asyncio.create_task(worker.run_forever())
        try:
            await shutdown.wait()
        finally:
            worker_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await worker_task

    async def _run_sweeper() -> None:
        sweeper_task = asyncio.create_task(
            run_sweeper_loop(
                sessionmaker=sessionmaker,
                senders=worker.senders,
                worker_id=worker.worker_id,
            )
        )
        try:
            await shutdown.wait()
        finally:
            sweeper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper_task

    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_run_worker())
            tg.create_task(_run_sweeper())
    finally:
        await worker.close()
        await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
