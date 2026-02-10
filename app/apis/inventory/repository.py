from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.inventory.exceptions import InventoryItemNameConflict
from app.apis.inventory.models import InventoryExpiryAlert, InventoryItem
from app.apis.inventory.schema import ExpiryFilter, InventoryFilters
from app.apis.inventory.types import InventoryAlertType
from app.core.database.base import HomeId, InventoryExpiryAlertId, InventoryId
from app.core.database.pagination import Page


class InventoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, item: InventoryItem) -> InventoryItem:
        self.session.add(item)
        await self.session.flush()
        await self.session.refresh(item)
        return item

    async def get_by_id(self, item_id: InventoryId) -> InventoryItem | None:
        return await self.session.get(InventoryItem, item_id)

    async def name_exists(
        self,
        *,
        home_id: HomeId,
        name: str,
        exclude_id: InventoryId | None = None,
    ) -> bool:
        stmt = sa.select(InventoryItem.id).where(
            InventoryItem.home_id == home_id,
            InventoryItem.name == name,
        )
        if exclude_id is not None:
            stmt = stmt.where(InventoryItem.id != exclude_id)
        return (await self.session.scalar(stmt)) is not None

    async def delete(self, item: InventoryItem) -> None:
        await self.session.delete(item)

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
        limit: int = 500,
    ) -> list[InventoryExpiryAlertId]:
        where_clauses: list[sa.ColumnElement[bool]] = [
            InventoryItem.expiry_date.isnot(None),
        ]
        if home_id is not None:
            where_clauses.append(InventoryItem.home_id == home_id)

        if alert_type == InventoryAlertType.EXPIRED:
            where_clauses.append(InventoryItem.expiry_date < today)

        elif alert_type == InventoryAlertType.EXPIRING_SOON:
            where_clauses.append(
                InventoryItem.expiry_date.between(today, today + timedelta(days=days))
            )
        else:
            raise ValueError("invalid alert_type")
        candidate_ids = list(
            (
                await self.session.execute(
                    sa.select(InventoryItem.id)
                    .where(*where_clauses)
                    .order_by(
                        InventoryItem.expiry_date.asc(),
                        InventoryItem.created_at.asc(),
                    )
                    .limit(limit)
                )
            ).scalars()
        )

        if not candidate_ids:
            return []

        rows = [
            {
                "id": uuid4(),
                "inventory_item_id": item_id,
                "alert_type": alert_type,
                "alert_date": today,
            }
            for item_id in candidate_ids
        ]

        insert_stmt = (
            pg_insert(InventoryExpiryAlert)
            .values(rows)
            .on_conflict_do_nothing(constraint="uq_item_alert_once_per_day")
            .returning(InventoryExpiryAlert.id)
        )

        alert_ids = list((await self.session.execute(insert_stmt)).scalars().all())
        return alert_ids

    async def get_unpublished_alerts_with_items(
        self,
        *,
        alert_type: InventoryAlertType | None = None,
        home_id: HomeId | None = None,
        limit: int = 500,
        max_attempts: int = 5,
    ) -> list[tuple[InventoryExpiryAlert, InventoryItem]]:
        """
        Fetch alert rows that still need publishing, with their InventoryItem.
        Returns [(alert, item), ...]
        """
        where_clauses: list[sa.ColumnElement[bool]] = [
            InventoryExpiryAlert.published_at.is_(None),
            InventoryExpiryAlert.publish_attempts < max_attempts,
        ]
        if alert_type is not None:
            where_clauses.append(InventoryExpiryAlert.alert_type == alert_type)
        if home_id is not None:
            where_clauses.append(InventoryItem.home_id == home_id)

        stmt = (
            sa.select(InventoryExpiryAlert, InventoryItem)
            .join(
                InventoryItem,
                InventoryExpiryAlert.inventory_item_id == InventoryItem.id,
            )
            .where(*where_clauses)
            .order_by(
                InventoryExpiryAlert.alert_date.asc(), InventoryExpiryAlert.id.asc()
            )
            .limit(limit)
        )
        print("#" * 8 + "Fetch unpublished alerts with items" + "#" * 8)
        stmt = stmt.with_for_update(skip_locked=True)

        rows = (await self.session.execute(stmt)).all()
        print(rows)
        return [(alert, item) for alert, item in rows]

    async def mark_alerts_published(
        self,
        *,
        alert_ids: Sequence[InventoryExpiryAlertId],
        now: datetime | None = None,
    ) -> int:
        if not alert_ids:
            return 0
        now = now or datetime.now(timezone.utc)

        stmt = (
            sa.update(InventoryExpiryAlert)
            .where(InventoryExpiryAlert.id.in_(list(alert_ids)))
            .where(InventoryExpiryAlert.published_at.is_(None))
            .values(
                published_at=now,
                publish_attempts=InventoryExpiryAlert.publish_attempts + 1,
                last_publish_error=None,
            )
        )
        res = await self.session.execute(stmt)
        return int(res.rowcount or 0)

    async def mark_alerts_failed(
        self,
        *,
        alert_ids: Sequence[InventoryExpiryAlertId],
        error: str,
    ) -> int:
        if not alert_ids:
            return 0

        error = (error or "")[:2000]

        stmt = (
            sa.update(InventoryExpiryAlert)
            .where(InventoryExpiryAlert.id.in_(list(alert_ids)))
            .where(InventoryExpiryAlert.published_at.is_(None))
            .values(
                publish_attempts=InventoryExpiryAlert.publish_attempts + 1,
                last_publish_error=error,
            )
        )
        res = await self.session.execute(stmt)
        return int(res.rowcount or 0)
