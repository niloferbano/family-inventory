from __future__ import annotations

import logging
from math import ceil

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homes.exceptions import HomeNotFound
from app.apis.homes.repository import HomeRepository
from app.apis.homeuser.repository import HomeUserRepository
from app.apis.household_categories.repository import HouseholdCategoryRepository
from app.apis.inventory.exceptions import (
    InventoryAccessDenied,
    InventoryCategoryInvalid,
    InventoryItemNotFound,
)
from app.apis.inventory.models import InventoryItem
from app.apis.inventory.repository import InventoryRepository
from app.apis.inventory.schema import (
    InventoryCreateRequest,
    InventoryCreateResponse,
    InventoryFilters,
    InventoryGetResponse,
    InventoryUpdateRequest,
    PaginatedInventoryItemResponse,
)
from app.apis.product.exceptions import ProductNotFound
from app.apis.product.repository import ProductRepository
from app.core.database.base import HomeId, InventoryId, ProductId
from app.core.database.pagination import Page, update_pagination

logger = logging.getLogger(__name__)


class InventoryService:
    def __init__(
        self,
        session: AsyncSession,
        current_user,
    ):
        self.session = session
        self.current_user = current_user
        self.inventory_repo = InventoryRepository(session=session)
        self.home_user_repo = HomeUserRepository(session=session)
        self.home_repo = HomeRepository(session=session)

    async def add_items(
        self,
        home_id: HomeId,
        items: list[InventoryCreateRequest],
    ) -> list[InventoryCreateResponse]:
        home = await self.home_repo.get_by_id(home_id)
        if not home:
            raise HomeNotFound(home_id=str(home_id))
        is_owner = await self.home_user_repo.user_is_owner(
            self.current_user.id, home_id
        )

        if not (self.current_user.is_admin or is_owner):
            raise InventoryAccessDenied(home_id=str(home_id))

        categories = await HouseholdCategoryRepository(self.session).lock_for_inventory(
            home_id, {item.household_category_id for item in items}
        )
        allowed = {category.id for category in categories}
        if any(item.household_category_id not in allowed for item in items):
            raise InventoryCategoryInvalid()

        products = await ProductRepository(self.session).get_many(
            {ProductId(item.product_id) for item in items}
        )
        valid_product_ids = {product.id for product in products}
        for item in items:
            if item.product_id not in valid_product_ids:
                raise ProductNotFound(product_id=str(item.product_id))

        models = [
            InventoryItem(
                home_id=home_id,
                created_by=self.current_user.id,
                **item.model_dump(),
            )
            for item in items
        ]

        try:
            created = await self.inventory_repo.add_items(home_id, models)
            return [InventoryCreateResponse.model_validate(i) for i in created]
        except IntegrityError:
            # household_category_id and product_id are both pre-checked above,
            # but a concurrent delete between that check and this insert can
            # still raise an IntegrityError (FK violation) here.
            await self.session.rollback()
            raise

    async def get_items(
        self,
        home_id: HomeId,
        pagination: Page,
        request_url: str,
        filters: InventoryFilters | None = None,
    ) -> PaginatedInventoryItemResponse:
        if not await self.home_user_repo.user_has_access(
            user_id=self.current_user.id,
            home_id=home_id,
        ):
            raise InventoryAccessDenied(home_id=str(home_id))

        filters = filters or InventoryFilters()

        rows, total = await self.inventory_repo.get_by_home(
            home_id,
            pagination=pagination,
            filters=filters,
        )

        total_pages = ceil(total / pagination.page_size) if total else 0

        next_url = (
            update_pagination(request_url, pagination.page + 1, pagination.page_size)
            if pagination.page < total_pages
            else None
        )
        prev_url = (
            update_pagination(request_url, pagination.page - 1, pagination.page_size)
            if pagination.page > 1
            else None
        )

        return PaginatedInventoryItemResponse(
            count=total,
            total_pages=total_pages,
            next=next_url,
            previous=prev_url,
            results=[InventoryGetResponse.model_validate(item) for item in rows],
        )

    async def update_item(
        self,
        *,
        home_id: HomeId,
        item_id: InventoryId,
        payload: InventoryUpdateRequest,
    ) -> InventoryItem:
        item = await self.inventory_repo.get_by_id(item_id)
        if not item or item.home_id != home_id:
            raise InventoryItemNotFound(item_id=str(item_id))

        is_owner = await self.home_user_repo.user_is_owner(
            self.current_user.id, home_id
        )
        if not (self.current_user.is_admin or is_owner):
            raise InventoryAccessDenied(home_id=str(home_id))

        updates = payload.model_dump(exclude_unset=True)
        if "household_category_id" in updates:
            if updates["household_category_id"] is None:
                raise InventoryCategoryInvalid()
            categories = await HouseholdCategoryRepository(
                self.session
            ).lock_for_inventory(home_id, {updates["household_category_id"]})
            if updates["household_category_id"] not in {
                category.id for category in categories
            }:
                raise InventoryCategoryInvalid()
        if not updates:
            return item

        if "product_id" in updates:
            product = await ProductRepository(self.session).get_by_id(
                updates["product_id"]
            )
            if product is None:
                raise ProductNotFound(product_id=str(updates["product_id"]))

        for field, value in updates.items():
            setattr(item, field, value)

        await self.session.flush()
        return item

    async def delete_item(
        self,
        *,
        home_id: HomeId,
        item_id: InventoryId,
    ) -> None:
        item = await self.inventory_repo.get_by_id(item_id)
        if not item or item.home_id != home_id:
            raise InventoryItemNotFound(item_id=str(item_id))

        is_owner = await self.home_user_repo.user_is_owner(
            self.current_user.id, home_id
        )
        if not (self.current_user.is_admin or is_owner):
            raise InventoryAccessDenied(home_id=str(home_id))

        await self.inventory_repo.delete(item)
