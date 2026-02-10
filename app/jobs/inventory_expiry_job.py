import asyncio
import logging
from datetime import date
from uuid import UUID

from app.apis.inventory.repository import InventoryRepository
from app.apis.inventory.services.expiry_service import InventoryExpiryService
from app.apis.inventory.types import InventoryAlertType
from app.apis.notifications.brokers import (EventBroker, LogBroker,
                                            RabbitMQBroker)
from app.core.configs.config import settings
from app.core.database.base import InventoryExpiryAlertId
from app.core.database.session import get_db

logger = logging.getLogger(__name__)

# Only time out the broker publish (and any non-DB work inside publish_expiry_event).
# IMPORTANT: do NOT wrap DB session checkout/transactions in a short timeout, or you can
# cancel while acquiring a pooled connection (causing CancelledError + leaked connections).
PUBLISH_TIMEOUT_S = 10.0  # per publish call (after DB session is acquired)

# Keep this <= your SQLAlchemy pool_size (+ small overflow). Start low and tune up.
CONCURRENCY = 5  # semaphore limit
MAX_BATCHES = 100  # safety limit to prevent infinite loop if something goes wrong. With CONCURRENCY=5 and limit=100, this allows up to 50k alerts per run (but will stop sooner if we hit an empty batch).


async def run_inventory_expiry_job(
    *,
    days: int = 7,
    limit: int = 100,
    broker: EventBroker | None = None,
) -> None:
    db = get_db()
    broker = broker or LogBroker()

    try:
        await db.connect()
        await broker.connect()
        today = date.today()

        # 1) Register alerts (DB transaction) -> returns ALERT IDS (InventoryExpiryAlert.id)
        async with db.begin() as session:
            repo = InventoryRepository(session)

            expiring_alert_ids: list[UUID] = await repo.register_expiry_alerts(
                alert_type=InventoryAlertType.EXPIRING_SOON,
                today=today,
                days=days,
                limit=limit,
            )
            expired_alert_ids: list[UUID] = await repo.register_expiry_alerts(
                alert_type=InventoryAlertType.EXPIRED,
                today=today,
                limit=limit,
            )

        logger.info(
            "Inventory expiry job registered alerts: expiring=%d expired=%d",
            len(expiring_alert_ids),
            len(expired_alert_ids),
        )

        if not expiring_alert_ids and not expired_alert_ids:
            logger.info("Inventory expiry job: nothing new to publish")
            return

        # 2) Publish + mark results for each alert type

        async def _publish_and_mark(alert_type: InventoryAlertType) -> int:
            published_count = 0
            batches_processed = 0

            sem = asyncio.Semaphore(CONCURRENCY)

            async def _publish_one(
                alert, item
            ) -> tuple[InventoryExpiryAlertId, Exception | None]:
                """Publish a single alert.

                NOTE: We intentionally acquire the DB session/connection *outside* the timeout.
                Timeouts should not cancel connection checkout or transactional cleanup.
                """
                async with sem:
                    try:
                        # Acquire DB session/connection first (no short timeout here).
                        async with db.begin() as session:
                            expiry_service = InventoryExpiryService(
                                session=session,
                                broker=broker,
                            )

                            # Apply timeout only to the publish call itself.
                            async with asyncio.timeout(PUBLISH_TIMEOUT_S):
                                await expiry_service.publish_expiry_event(
                                    item=item,
                                    alert_type=alert_type,
                                )

                        return alert.id, None
                    except Exception as exc:
                        return alert.id, exc

            while batches_processed < MAX_BATCHES:
                batches_processed += 1

                # 1) Fetch unpublished alerts+items (DB txn)
                async with db.begin() as session:
                    repo = InventoryRepository(session)
                    rows = await repo.get_unpublished_alerts_with_items(
                        alert_type=alert_type,
                        limit=limit,
                    )

                if not rows:
                    return published_count

                # 2) Publish concurrently (no DB txn), collect results as they finish
                tasks = [
                    asyncio.create_task(_publish_one(alert, item))
                    for alert, item in rows
                ]

                published_ids: list[InventoryExpiryAlertId] = []
                failed_ids: list[InventoryExpiryAlertId] = []
                failed_err: dict[InventoryExpiryAlertId, str] = {}

                try:
                    for t in asyncio.as_completed(tasks):
                        alert_id, exc = await t
                        if exc is None:
                            published_ids.append(alert_id)
                        else:
                            failed_ids.append(alert_id)
                            failed_err[alert_id] = f"{type(exc).__name__}: {exc}"
                            logger.exception(
                                "Failed to publish %s alert=%s",
                                alert_type.value,
                                str(alert_id),
                                exc_info=exc,
                            )
                except asyncio.CancelledError:
                    # Ensure in-flight publish tasks are cancelled so we don't leak work.
                    for t in tasks:
                        t.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
                    raise
                finally:
                    # Defensive cleanup: in case we exit early due to an exception.
                    pending = [t for t in tasks if not t.done()]
                    if pending:
                        for t in pending:
                            t.cancel()
                        await asyncio.gather(*pending, return_exceptions=True)

                # 3) Mark results (DB txn)
                async with db.begin() as session:
                    repo = InventoryRepository(session)

                    if published_ids:
                        await repo.mark_alerts_published(alert_ids=published_ids)
                        published_count += len(published_ids)

                    if failed_ids:
                        combined = "; ".join(list(failed_err.values())[:3])
                        await repo.mark_alerts_failed(
                            alert_ids=failed_ids, error=combined
                        )

            # If we hit MAX_BATCHES, we intentionally stop and let the *next cron run* continue.
            logger.warning(
                "Reached MAX_BATCHES=%d for alert_type=%s. Remaining unpublished will be processed next run.",
                MAX_BATCHES,
                alert_type.value,
            )
            return published_count

        expiring_published = await _publish_and_mark(InventoryAlertType.EXPIRING_SOON)
        expired_published = await _publish_and_mark(InventoryAlertType.EXPIRED)

        logger.info(
            "Inventory expiry job: published expiring=%d expired=%d",
            expiring_published,
            expired_published,
        )

    finally:
        await broker.close()
        await db.disconnect()


if __name__ == "__main__":
    rabbit = RabbitMQBroker(
        amqp_url=settings.RABBITMQ_URL,
        exchange_name=settings.NOTIFICATION_EXCHANGE,
    )
    asyncio.run(run_inventory_expiry_job(days=7, limit=100, broker=rabbit))
