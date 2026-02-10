from __future__ import annotations

import asyncio
import contextlib
import signal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.apis.notifications.brokers import RabbitMQBroker
from app.apis.notifications.worker.consumer import (NotificationWorker,
                                                    WorkerConfig)
from app.apis.notifications.worker.sweeper import run_sweeper_loop
from app.core.configs.config import settings
from app.core.database.session import get_db
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def main() -> None:
    db = get_db()
    # Ensure the DB engine/pool is initialized for standalone worker runs.
    await db.connect()

    # DB sessionmaker for the worker
    sessionmaker: async_sessionmaker[AsyncSession] = db.sessionmaker

    cfg = WorkerConfig(
        amqp_url=settings.RABBITMQ_URL,
        exchange_name=settings.NOTIFICATION_EXCHANGE,
        queue_name=settings.NOTIFICATION_QUEUE,
        bindings=settings.notification_bindings_list(),
        dlx_name=settings.NOTIFICATION_DLX,
        dlq_name=settings.NOTIFICATION_DLQ,
        dlq_routing_key=settings.NOTIFICATION_DLQ_ROUTING_KEY,
        retry_exchange_name=settings.NOTIFICATION_RETRY_EXCHANGE,
        retry_rk_30s=settings.NOTIFICATION_RETRY_ROUTING_KEY_30S,
        retry_return_topic=settings.NOTIFICATION_RETRY_RETURN_TOPIC,
        prefetch=20,
        max_retries=5,
        use_broker_retries=settings.BROKER_MANAGED_RETRIES,
    )

    worker = NotificationWorker(cfg=cfg, sessionmaker=sessionmaker)
    await worker.connect_with_retry()

    shutdown = asyncio.Event()

    def _request_shutdown() -> None:
        shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, _request_shutdown)

    async def _run_worker() -> None:
        await worker.run_forever()

    async def _run_sweeper() -> None:
        broker = RabbitMQBroker(
            amqp_url=settings.RABBITMQ_URL,
            exchange_name=settings.NOTIFICATION_EXCHANGE,
        )
        try:
            connect = getattr(broker, "connect", None)
            if callable(connect):
                res = connect()
                if asyncio.iscoroutine(res):
                    await res
            await run_sweeper_loop(
                sessionmaker=sessionmaker,
                senders=worker.senders,
                worker_id=worker.worker_id,
                broker=broker,
            )
        finally:
            # If the broker exposes an async close(), clean it up.
            close = getattr(broker, "close", None)
            if callable(close):
                res = close()
                if asyncio.iscoroutine(res):
                    await res

    worker_task: asyncio.Task | None = None
    sweeper_task: asyncio.Task | None = None

    def _task_done_callback(task: asyncio.Task) -> None:
        # If any background task crashes, trigger shutdown.
        with contextlib.suppress(asyncio.CancelledError):
            exc = task.exception()
            if exc is not None:
                logger.exception("Background task crashed: %s", exc)
                shutdown.set()

    try:
        worker_task = asyncio.create_task(_run_worker(), name="notification-worker")
        sweeper_task = asyncio.create_task(_run_sweeper(), name="notification-sweeper")

        worker_task.add_done_callback(_task_done_callback)
        sweeper_task.add_done_callback(_task_done_callback)

        # Block until we receive SIGINT/SIGTERM or a task crashes.
        await shutdown.wait()

    finally:
        # 1) Stop consuming so no new DB work starts
        with contextlib.suppress(Exception):
            await worker.stop_consuming()

        # 2) Give in-flight message handlers a chance to finish
        with contextlib.suppress(Exception):
            await worker.drain(timeout=10.0)

        # 3) Now cancel background loops (safe: they’re not starting new work)
        for t in (worker_task, sweeper_task):
            if t:
                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t

        # 4) Close broker, then DB
        await worker.close()
        await db.disconnect()


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
