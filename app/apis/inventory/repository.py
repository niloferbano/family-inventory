from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.inventory.exceptions import InventoryItemNameConflict
from app.apis.inventory.models import InventoryItem
from app.apis.inventory.schema import ExpiryFilter
from app.core.database.base import HomeId
from app.core.database.pagination import Page


class InventoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, item: InventoryItem) -> InventoryItem:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def add_items(
        self, home_id: HomeId, items: list[InventoryItem]
    ) -> list[InventoryItem] | None:
        names = [item.name for item in items]

        existing = await self.session.execute(
            sa.select(InventoryItem.name)
            .where(InventoryItem.home_id == home_id)
            .where(InventoryItem.name.in_(names))
        )

        existing_names = existing.scalars().all()

        new_items = [i for i in items if i.name not in existing_names]

        if not new_items:
            raise InventoryItemNameConflict(existing_names)

        self.session.add_all(items)
        await self.session.flush()
        return items

    async def get_by_home(
        self,
        home_id,
        pagination: Page,
        expiry: ExpiryFilter | None = None,
        days: int = 7,
    ):
        today = date.today()
        limit, offset = pagination.to_limit()
        limit, offset = pagination.to_limit()
        base_query = sa.select(InventoryItem).where(InventoryItem.home_id == home_id)
        if expiry == ExpiryFilter.EXPIRED:
            base_query = base_query.where(
                InventoryItem.expiry_date.isnot(None),
                InventoryItem.expiry_date < today,
            )

        elif expiry == ExpiryFilter.EXPIRING_SOON:
            base_query = base_query.where(
                InventoryItem.expiry_date.isnot(None),
                InventoryItem.expiry_date.between(
                    today,
                    today + timedelta(days=days),
                ),
            )
        count_query = (
            sa.select(sa.func.count())
            .select_from(InventoryItem)
            .where(InventoryItem.home_id == home_id)
        )
        total = (await self.session.execute(count_query)).scalar() or 0
        paginated_query = (
            base_query.order_by(InventoryItem.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        rows = (await self.session.execute(paginated_query)).scalars().all()

        return rows, total
