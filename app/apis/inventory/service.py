from math import ceil

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.apis.homeuser.repository import HomeUserRepository
from app.apis.inventory.exceptions import (InventoryAccessDenied,
                                           InventoryItemNameConflict)
from app.apis.inventory.models import InventoryItem
from app.apis.inventory.repository import InventoryRepository
from app.apis.inventory.schema import (InventoryCreateRequest,
                                       InventoryCreateResponse,
                                       InventoryGetResponse,
                                       PaginatedInventorytItemResponse)
from app.core.database.base import HomeId
from app.core.database.pagination import Page, update_pagination


class InventoryService:
    def __init__(self, session, current_user):
        self.session = session
        self.current_user = current_user
        self.inventory_repo = InventoryRepository(session=session)
        self.home_user_repo = HomeUserRepository(session=session)

    async def add_items(
        self,
        home_id: HomeId,
        items: list[InventoryCreateRequest],
    ):
        models = [
            InventoryItem(
                home_id=home_id,
                created_by=self.current_user.id,
                **item.model_dump(),
            )
            for item in items
        ]

        try:
            items = await self.inventory_repo.add_items(home_id, models)
            return [InventoryCreateResponse.model_validate(i) for i in items]

        except IntegrityError:
            existing = await self.inventory_repo.get_existing_names(
                home_id,
                [i.name for i in models],
            )

            raise InventoryItemNameConflict(existing)

    async def get_items(
        self, home_id, pagination: Page, request_url: str, expiry=None, days=7
    ) -> PaginatedInventorytItemResponse:
        if not await self.home_user_repo.user_has_access(
            user_id=self.current_user.id,
            home_id=home_id,
        ):
            raise InventoryAccessDenied(
                home_id=str(home_id),
            )
        rows, total = await self.inventory_repo.get_by_home(
            home_id,
            pagination=pagination,
            expiry=expiry,
            days=days,
        )
        total_pages = ceil(total / pagination.page_size)

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
        return PaginatedInventorytItemResponse(
            count=total,
            total_pages=total_pages,
            next=next_url,
            previous=prev_url,
            results=[InventoryGetResponse.model_validate(item) for item in rows],
        )

    async def get_existing_names(
        self,
        home_id: HomeId,
        names: list[str],
    ) -> list[str]:
        result = await self.session.execute(
            select(InventoryItem.name).where(
                InventoryItem.home_id == home_id,
                InventoryItem.name.in_(names),
            )
        )
        return [row[0] for row in result.all()]
