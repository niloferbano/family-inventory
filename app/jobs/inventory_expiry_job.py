import asyncio
import logging

from app.apis.inventory.expiry_service import InventoryExpiryService
from app.apis.inventory.types import InventoryAlertType
from app.apis.notifications.brokers import LogBroker, RabbitMQBroker
from app.core.configs.config import settings
from app.core.database.session import get_db
from app.core.messaging.broker import EventBroker

logger = logging.getLogger(__name__)


async def run_inventory_expiry_job(
    *,
    days: int = 7,
    limit: int = 100,
    broker: EventBroker | None = None,
) -> None:
    db = get_db()

    # Standalone script: lifespan won't run, so we connect here.
    broker = broker or LogBroker()
    await broker.connect()

    try:
        # 1) DB work (scan + register alerts) in one transaction
        async with db.begin() as session:
            expiry_service = InventoryExpiryService(session=session, broker=broker)
            batch = await expiry_service.collect_expiry_alerts(days=days, limit=limit)

        expiring = batch.expiring_soon
        expired = batch.expired

        logger.info(
            "Inventory expiry job completed: expiring=%d expired=%d",
            len(expiring),
            len(expired),
        )

        if not expiring and not expired:
            logger.info("Inventory expiry job: nothing new to publish")
            return

        # 2) Publish events (NO DB transaction held open)
        async def _publish_items(items, alert_type: InventoryAlertType) -> None:
            if not items:
                return
            async with asyncio.TaskGroup() as tg:
                for item in items:
                    tg.create_task(
                        expiry_service.publish_expiry_event(
                            item=item,
                            alert_type=alert_type,
                        )
                    )

        # Note: publish_expiry_event only uses broker, not DB
        await asyncio.gather(
            _publish_items(expiring, InventoryAlertType.EXPIRING_SOON),
            _publish_items(expired, InventoryAlertType.EXPIRED),
        )

        logger.info(
            "Inventory expiry job: published %d expiring_soon, %d expired",
            len(expiring),
            len(expired),
        )

    finally:
        await broker.close()
        # optional for a one-off script
        await db.disconnect()


if __name__ == "__main__":
    rabbit = RabbitMQBroker(
        amqp_url=settings.RABBITMQ_URL,
        exchange_name=settings.NOTIFICATION_EXCHANGE,
    )
    asyncio.run(run_inventory_expiry_job(days=7, limit=100, broker=rabbit))
