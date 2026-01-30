from __future__ import annotations

import logging
from math import ceil

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.apis.homes.exceptions import HomeNotFound
from app.apis.homes.repository import HomeRepository
from app.apis.homeuser.repository import HomeUserRepository
from app.apis.inventory.exceptions import (InventoryAccessDenied,
                                           InventoryItemNameConflict)
from app.apis.inventory.models import InventoryItem
from app.apis.inventory.repository import InventoryRepository
from app.apis.inventory.schema import (InventoryCreateRequest,
                                       InventoryCreateResponse,
                                       InventoryFilters, InventoryGetResponse,
                                       PaginatedInventoryItemResponse)
from app.core.database.base import HomeId
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

        except IntegrityError as exc:
            # If you *continue using this session*, you must rollback.
            await self.session.rollback()

            existing = await self.inventory_repo.get_existing_names(
                home_id,
                [i.name for i in models],
            )
            raise InventoryItemNameConflict(existing) from exc

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
