from datetime import date, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.inventory.exceptions import InventoryItemNameConflict
from app.apis.inventory.models import InventoryExpiryAlert, InventoryItem
from app.apis.inventory.schema import ExpiryFilter, InventoryFilters
from app.apis.inventory.types import InventoryAlertType
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

        self.session.add_all(new_items)
        await self.session.flush()
        return new_items

    async def get_by_home(
        self,
        home_id: HomeId,
        pagination: Page,
        filters: InventoryFilters,
    ):
        today = date.today()
        limit, offset = pagination.to_limit()

        where_clauses: list[sa.ColumnElement[bool]] = [InventoryItem.home_id == home_id]

        if filters.expiry == ExpiryFilter.EXPIRED:
            where_clauses += [
                InventoryItem.expiry_date.isnot(None),
                InventoryItem.expiry_date < today,
            ]

        elif filters.expiry == ExpiryFilter.EXPIRING_SOON:
            where_clauses += [
                InventoryItem.expiry_date.isnot(None),
                InventoryItem.expiry_date.between(
                    today,
                    today + timedelta(days=filters.days),
                ),
            ]

        if filters.category:
            where_clauses.append(InventoryItem.category.in_(filters.category))

        base_query = sa.select(InventoryItem).where(*where_clauses)

        count_query = sa.select(sa.func.count()).select_from(base_query.subquery())
        total = (await self.session.execute(count_query)).scalar_one()

        rows_query = (
            base_query.order_by(InventoryItem.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = (await self.session.execute(rows_query)).scalars().all()

        return rows, total

    async def get_existing_names(
        self,
        home_id: HomeId,
        names: list[str],
    ) -> list[str]:
        result = await self.session.execute(
            sa.select(InventoryItem.name).where(
                InventoryItem.home_id == home_id,
                InventoryItem.name.in_(names),
            )
        )
        return list(result.scalars().all())

    async def register_expiry_alerts(
        self,
        *,
        alert_type: InventoryAlertType,
        today: date,
        days: int = 7,
        home_id: HomeId | None = None,
    ) -> list[InventoryItem]:
        q = sa.select(InventoryItem).where(InventoryItem.expiry_date.isnot(None))

        if home_id is not None:
            q = q.where(InventoryItem.home_id == home_id)  # ✅ must reassign

        if alert_type == InventoryAlertType.EXPIRED:
            q = q.where(InventoryItem.expiry_date < today)

        elif alert_type == InventoryAlertType.EXPIRING_SOON:
            q = q.where(
                InventoryItem.expiry_date.between(today, today + timedelta(days=days))
            )
        else:
            raise ValueError("invalid alert_type")

        items = (await self.session.execute(q)).scalars().all()
        if not items:
            return []

        rows = [
            {
                "inventory_item_id": item.id,
                "alert_type": alert_type,  # ✅ store string in DB
                "alert_date": today,
            }
            for item in items
        ]

        stmt = (
            pg_insert(InventoryExpiryAlert)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_item_alert_once_per_day")
            .returning(InventoryExpiryAlert.inventory_item_id)
        )

        inserted_ids = (await self.session.execute(stmt)).scalars().all()
        if not inserted_ids:
            return []

        inserted_set = set(inserted_ids)
        return [item for item in items if item.id in inserted_set]
