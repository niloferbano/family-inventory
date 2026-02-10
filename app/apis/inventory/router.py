from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.apis.errors.errors import ErrorResponse
from app.apis.inventory.schema import (ExpiryFilter, InventoryCreateRequest,
                                       InventoryCreateResponse,
                                       InventoryFilters, InventoryGetResponse,
                                       InventoryUpdateRequest,
                                       PaginatedInventoryItemResponse)
from app.apis.inventory.services.service import InventoryService
from app.apis.inventory.types import InventoryCategory
from app.core.database.base import HomeId, InventoryId
from app.core.database.pagination import PaginationParams, get_pagination
from app.core.database.session import get_db
from app.iam.dependencies import get_current_user

router = APIRouter(prefix="/inventory", tags=["Inventory"])


@router.post("/{home_id}", response_model=list[InventoryCreateResponse])
async def add_inventory_item(
    home_id: HomeId,
    payload: list[InventoryCreateRequest],
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = InventoryService(session, current_user)
        return await service.add_items(home_id, payload)


@router.get(
    "/{home_id}",
    response_model=PaginatedInventoryItemResponse,
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def list_inventory_items(
    home_id: HomeId,
    request: Request,
    pagination_params: PaginationParams = Depends(),
    expiry: ExpiryFilter | None = Query(default=None),
    days: int = Query(default=7, ge=1, le=365),
    category: list[InventoryCategory] | None = Query(default=None),
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    pagination = get_pagination(
        page=pagination_params.page,
        page_size=pagination_params.page_size,
    )
    filters = InventoryFilters(
        category=category,
        expiry=expiry,
        days=days,
    )
    async with db_manager.begin() as session:
        service = InventoryService(session, current_user)
        try:
            return await service.get_items(
                home_id=home_id,
                pagination=pagination,
                request_url=str(request.url),
                filters=filters,
            )
        except PermissionError:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User doesn't have access",
            )


@router.patch("/{home_id}/{item_id}", response_model=InventoryGetResponse)
async def update_inventory_item(
    home_id: HomeId,
    item_id: InventoryId,
    payload: InventoryUpdateRequest,
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = InventoryService(session, current_user)
        item = await service.update_item(
            home_id=home_id,
            item_id=item_id,
            payload=payload,
        )
        return InventoryGetResponse.model_validate(item)


@router.delete("/{home_id}/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    home_id: HomeId,
    item_id: InventoryId,
    db_manager=Depends(get_db),
    current_user=Depends(get_current_user),
):
    async with db_manager.begin() as session:
        service = InventoryService(session, current_user)
        await service.delete_item(home_id=home_id, item_id=item_id)
        return
