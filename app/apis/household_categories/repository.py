from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.household_categories.exceptions import HouseholdCategoryNameConflict
from app.apis.household_categories.models import HouseholdCategory
from app.core.database.base import HomeId, HouseholdCategoryId


class HouseholdCategoryRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, category: HouseholdCategory) -> HouseholdCategory:
        # category.id may be unset: mapped_column(default=uuid4) is applied by
        # the ORM unit-of-work on flush, not on a bare unflushed instance, and
        # this uses a Core insert (for on_conflict_do_nothing) instead of
        # session.add()+flush, so we generate it ourselves when missing.
        category_id = category.id or uuid4()
        insert_stmt = (
            pg_insert(HouseholdCategory)
            .values(
                id=category_id,
                home_id=category.home_id,
                name=category.name,
            )
            .on_conflict_do_nothing(constraint="uq_household_category_home_name")
            .returning(HouseholdCategory.id)
        )
        created_id = (await self.session.execute(insert_stmt)).scalar_one_or_none()
        if created_id is None:
            raise HouseholdCategoryNameConflict(category.name)
        await self.session.flush()
        return await self.get_by_id(created_id)

    async def get_by_id(
        self, category_id: HouseholdCategoryId
    ) -> HouseholdCategory | None:
        return await self.session.get(HouseholdCategory, category_id)

    async def list_by_home(self, home_id: HomeId) -> list[HouseholdCategory]:
        stmt = (
            sa.select(HouseholdCategory)
            .where(HouseholdCategory.home_id == home_id)
            .order_by(HouseholdCategory.name.asc())
        )
        return list((await self.session.execute(stmt)).scalars().all())

    async def delete(self, category: HouseholdCategory) -> None:
        await self.session.delete(category)
