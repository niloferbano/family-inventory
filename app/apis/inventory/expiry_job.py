from __future__ import annotations

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.inventory.expiry_service import InventoryExpiryService
from app.apis.inventory.types import InventoryAlertType

logger = logging.getLogger(__name__)


class InventoryExpiryScanner:
    """
    Flow:
      1) DB session -> collect_expiry_alerts() (select + register alerts via ON CONFLICT)
      2) Publish events concurrently (no DB required)
    """

    def __init__(
        self,
        session: AsyncSession,
    ):
        self.expiry_service = InventoryExpiryService(session)

    async def run(self, *, days: int = 7, limit: int = 500) -> None:
        batch = await self.expiry_service.collect_expiry_alerts(days=days, limit=limit)

        expiring = batch.expiring_soon
        expired = batch.expired

        logger.info(
            "Expiry scan: expiring_soon=%d expired=%d",
            len(expiring),
            len(expired),
        )

        if not expiring and not expired:
            return

        async def _safe_publish(item, alert_type: InventoryAlertType) -> None:
            try:
                await self.expiry_service.publish_expiry_event(
                    item=item,
                    alert_type=alert_type,
                )
            except Exception:
                logger.exception(
                    "Failed to publish %s for item=%s",
                    alert_type.value,
                    getattr(item, "id", None),
                )

        async with asyncio.TaskGroup() as tg:
            for item in expiring:
                tg.create_task(_safe_publish(item, InventoryAlertType.EXPIRING_SOON))
            for item in expired:
                tg.create_task(_safe_publish(item, InventoryAlertType.EXPIRED))
